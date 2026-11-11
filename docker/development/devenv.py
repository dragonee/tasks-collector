#!/usr/bin/env python3
"""Development environments: git worktrees, each with a Docker Compose stack
of its own.

An environment is a worktree whose docker/development/.env sets
TASKS_PORT_PREFIX. The compose file turns the prefix into the stack's project
name and host ports: prefix 4 is the project tasks-4 with the app on 4000,
MinIO on 4900 and 4901 and the database MCP on 4079. The database and MinIO
data live in the worktree (docker/development/db and minio), are seeded on
the first start (seed_dev) and go away with it. The main checkout has no
prefix and keeps 8000, 9000, 9001 and 7079.

Inside an environment the usual commands reach its stack, since compose
reads that .env:

    docker compose -f docker/development/docker-compose.yml exec tasks-backend ...

Commands:

    start [NAME] [--prefix N] [--branch B] [--base REF]
        Create the worktree .claude/worktrees/NAME on a new branch NAME (or
        B) from REF (default: HEAD here), or take the worktree of that name or
        branch; give it a free prefix (or N), bring its stack up and wait
        until the app answers.
    list
        Every environment and the main checkout, with their state.
    status [ENV]
        Where an environment is and what runs in it.
    resume [ENV]
        Bring an environment's stack up again and wait for it.
    down [ENV] [--remove [--force]]
        Stop and remove its containers; the data stays in the worktree.
        --remove also removes the worktree, its data, and its branch when
        that is merged.

ENV is a prefix, a worktree name, a branch or a path. Left out, it is the
environment the current directory is in, or the only one there is.
--json prints the result as JSON on stdout; progress goes to stderr.
"""

import argparse
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PREFIX_VAR = "TASKS_PORT_PREFIX"
COMPOSE_FILE = "docker/development/docker-compose.yml"
ENV_FILE = "docker/development/.env"
WORKTREES = ".claude/worktrees"
BACKEND = "tasks-backend"
FRONTEND = "tasks-frontend"
# Written by the frontend's first build; pages can't render without it.
ASSETS = "tasks/static/local/app-js-tags.html"

# Prefix N puts ports at N000 to N999. 1 would need root for port 1000 on
# Linux, 65 would go past the last port, and 7, 8 and 9 overlap the main
# checkout's 7079, 8000, 9000 and 9001.
PREFIXES = [n for n in range(2, 65) if n not in (7, 8, 9)]

# Where the published ports are, as (service, container port).
URLS = {
    "app": (BACKEND, 8000, ""),
    "minio": ("tasks-minio", 9000, ""),
    "minio_console": ("tasks-minio", 9001, ""),
    "mcp": ("mcp-postgres", 8080, "/message"),
}
LOGIN = "django / django (alice / django is shared a board and an observation)"

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class DevenvError(Exception):
    pass


def note(message):
    print(message, file=sys.stderr, flush=True)


def run(cmd, cwd, env=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if check and result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        raise DevenvError(f"{' '.join(cmd)} failed:\n{output}")
    return result


def stream(cmd, cwd, env=None):
    """Run ``cmd`` with its output on stderr, keeping stdout for the result."""
    if subprocess.run(cmd, cwd=cwd, env=env, stdout=sys.stderr).returncode != 0:
        raise DevenvError(f"{' '.join(cmd)} failed (output above)")


def git(*args, cwd):
    return run(["git", *args], cwd=cwd).stdout.strip()


# Worktrees and environments


@dataclass
class Worktree:
    path: Path
    branch: str | None


@dataclass
class Env:
    path: Path
    branch: str | None
    prefix: int | None
    main: bool

    @property
    def name(self):
        return "main" if self.main else self.path.name


def main_checkout():
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=".")
    return Path(common).parent


def worktrees(main):
    found = []
    for block in git("worktree", "list", "--porcelain", cwd=main).split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        if "worktree" not in fields:
            continue
        branch = fields.get("branch", "").removeprefix("refs/heads/") or None
        found.append(Worktree(Path(fields["worktree"]), branch))
    return found


def read_prefix(path):
    try:
        lines = (path / ENV_FILE).read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() == PREFIX_VAR:
            value = value.strip().strip("\"'")
            return int(value) if value.isdigit() else None
    return None


def write_prefix(path, prefix):
    """Set the prefix in the worktree's .env, keeping what else it says."""
    file = path / ENV_FILE
    lines = file.read_text().splitlines() if file.exists() else []
    lines = [line for line in lines if line.partition("=")[0].strip() != PREFIX_VAR]
    lines.append(f"{PREFIX_VAR}={prefix}")
    file.write_text("\n".join(lines) + "\n")


def environments(main):
    """The main checkout first, then every worktree with a prefix."""
    envs = []
    for wt in worktrees(main):
        is_main = wt.path == main
        prefix = read_prefix(wt.path) if wt.path.exists() else None
        if is_main or prefix is not None:
            envs.append(Env(wt.path, wt.branch, prefix, is_main))
    return envs


def inside(path, directory):
    return path == directory or directory in path.parents


def select(envs, key, allow_main=False):
    """The environment ``key`` names, or the one the current directory is in,
    or the only one there is."""
    candidates = envs if allow_main else [e for e in envs if not e.main]
    if key is not None:
        for env in candidates:
            if key.isdigit() and env.prefix == int(key):
                return env
            if key in (env.name, env.branch) or Path(key).resolve() == env.path:
                return env
        raise DevenvError(f"No environment {key!r}.{known(envs)}")

    cwd = Path.cwd().resolve()
    # Most specific first: environments sit inside the main checkout.
    for env in sorted(candidates, key=lambda e: len(e.path.parts), reverse=True):
        if inside(cwd, env.path):
            return env
    prefixed = [e for e in candidates if not e.main]
    if len(prefixed) == 1:
        return prefixed[0]
    if not prefixed:
        raise DevenvError("There are no environments; start one.")
    raise DevenvError(f"Which environment?{known(envs)}")


def known(envs):
    names = [f"{e.prefix} ({e.name})" for e in envs if not e.main]
    return f" There are: {', '.join(names)}." if names else ""


# Docker


def compose_env(prefix):
    """The environment compose runs in: the prefix given, and never one left
    in the caller's shell."""
    env = dict(os.environ)
    env.pop(PREFIX_VAR, None)
    if prefix is not None:
        env[PREFIX_VAR] = str(prefix)
    return env


def compose(*args):
    return ["docker", "compose", "-f", COMPOSE_FILE, *args]


def resolved(path, prefix):
    """The project name and the published ports the compose file in ``path``
    gives ``prefix``: ({(service, container port): host port}, project)."""
    out = run(
        compose("config", "--format", "json"),
        cwd=path,
        env=compose_env(prefix),
    ).stdout
    config = json.loads(out)
    ports = {}
    for service, spec in config["services"].items():
        for port in spec.get("ports", []):
            if port.get("published"):
                ports[(service, int(port["target"]))] = int(port["published"])
    return config["name"], ports


@dataclass
class Container:
    project: str
    service: str
    state: str
    status: str


def containers():
    fmt = "\t".join(
        [
            '{{.Label "com.docker.compose.project"}}',
            '{{.Label "com.docker.compose.service"}}',
            '{{.Label "com.docker.compose.oneoff"}}',
            "{{.State}}",
            "{{.Status}}",
        ]
    )
    out = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=com.docker.compose.project",
            "--format",
            fmt,
        ],
        cwd=".",
    ).stdout
    found = []
    for line in out.splitlines():
        project, service, oneoff, state, status = line.split("\t")
        if oneoff != "True":
            found.append(Container(project, service, state, status))
    return found


def stack_state(project, all_containers):
    mine = [c for c in all_containers if c.project == project]
    if not mine:
        return "down"
    if not any(c.state == "running" for c in mine):
        return "stopped"
    # A one-off service (tasks-minio-init) is done once it exited with 0.
    finished = [
        c for c in mine if c.state == "exited" and c.status.startswith("Exited (0)")
    ]
    if all(c.state == "running" or c in finished for c in mine):
        return "up"
    return "partial"


def busy(port):
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket() as sock:
            try:
                sock.bind((host, port))
            except OSError:
                return True
    return False


def answers(url):
    try:
        urllib.request.urlopen(url, timeout=3).close()
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    except http.client.HTTPException:
        return False
    return True


# Prefixes


def check_prefix(prefix, path, envs, owner=None):
    """Raise unless ``prefix`` can be given to the environment at ``path``."""
    if prefix not in PREFIXES:
        raise DevenvError(
            f"Prefix {prefix} isn't one to use: 2 to 64, except 7, 8 and 9"
            " (the main checkout's ports)."
        )
    for env in envs:
        if env.prefix == prefix and env.path != owner:
            raise DevenvError(f"Prefix {prefix} is {env.name}'s ({env.path}).")
    _, ports = resolved(path, prefix)
    taken = sorted(port for port in ports.values() if busy(port))
    if taken:
        raise DevenvError(
            f"Prefix {prefix}: port {', '.join(map(str, taken))} is in use."
        )


def free_prefix(path, envs):
    claimed = {e.prefix for e in envs}
    for prefix in PREFIXES:
        if prefix in claimed:
            continue
        _, ports = resolved(path, prefix)
        if not any(busy(port) for port in ports.values()):
            return prefix
    raise DevenvError("No prefix is free.")


# Bringing a stack up


def summary(env, all_containers=None):
    project, ports = resolved(env.path, env.prefix)
    if all_containers is None:
        all_containers = containers()
    result = {
        "name": env.name,
        "prefix": env.prefix,
        "path": str(env.path),
        "branch": env.branch,
        "project": project,
        "status": stack_state(project, all_containers),
    }
    for key, (service, target, suffix) in URLS.items():
        if (service, target) in ports:
            result[key] = f"http://localhost:{ports[(service, target)]}{suffix}"
    result["login"] = LOGIN
    return result


def up(env, wait, timeout):
    project, ports = resolved(env.path, env.prefix)
    if env.prefix is not None and project != f"tasks-{env.prefix}":
        raise DevenvError(
            f"The compose file in {env.path} doesn't read {PREFIX_VAR}; bring"
            f" main's {COMPOSE_FILE} into this branch first."
        )

    running = [c for c in containers() if c.project == project and c.state == "running"]
    if not running:
        taken = sorted(port for port in ports.values() if busy(port))
        if taken:
            raise DevenvError(f"Port {', '.join(map(str, taken))} is in use.")

    note(f"Bringing up {project} in {env.path}")
    stream(compose("up", "-d"), cwd=env.path, env=compose_env(env.prefix))
    if wait:
        wait_until_ready(env, project, ports[(BACKEND, 8000)], timeout)
    return summary(env)


def wait_until_ready(env, project, port, timeout):
    url = f"http://localhost:{port}/"
    assets = env.path / ASSETS
    note(
        f"Waiting for {url} and the frontend build (a new environment installs"
        " packages, migrates and seeds first: a few minutes)"
    )
    deadline = time.monotonic() + timeout
    while not (answers(url) and assets.exists()):
        for c in containers():
            if (
                c.project == project
                and c.service in (BACKEND, FRONTEND)
                and c.state in ("exited", "dead")
            ):
                stream(
                    compose("logs", "--tail", "40", c.service),
                    cwd=env.path,
                    env=compose_env(env.prefix),
                )
                raise DevenvError(f"{c.service} stopped; its last lines are above.")
        if time.monotonic() > deadline:
            raise DevenvError(
                f"Not ready after {timeout}s. `resume` waits again; the logs:"
                f" docker compose -f {COMPOSE_FILE} logs {BACKEND} {FRONTEND}"
            )
        time.sleep(3)


def create_worktree(main, path, branch, base):
    exists = (
        run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=main,
            check=False,
        ).returncode
        == 0
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if exists:
        if base:
            raise DevenvError(f"Branch {branch} exists; --base is for a new branch.")
        note(f"Checking out {branch} in {path}")
        git("worktree", "add", str(path), branch, cwd=".")
    else:
        note(f"Creating branch {branch} from {base or 'HEAD'} in {path}")
        git("worktree", "add", "-b", branch, str(path), base or "HEAD", cwd=".")


# Commands


def cmd_start(args):
    main = main_checkout()
    envs = environments(main)

    name = args.name or (args.branch.replace("/", "-") if args.branch else None)
    if name is not None and (not NAME_RE.match(name) or name.isdigit()):
        raise DevenvError(
            f"{name!r} can't name a worktree: letters, digits, '.', '_' and '-',"
            " not just a number."
        )

    existing = None
    if name is not None:
        existing = next(
            (wt for wt in worktrees(main) if name in (wt.path.name, wt.branch)), None
        )
    if existing is not None and existing.path == main:
        raise DevenvError(
            "That is the main checkout; it runs on the default ports as it is."
        )

    env = next((e for e in envs if existing and e.path == existing.path), None)
    if env is not None:
        if args.prefix not in (None, env.prefix):
            raise DevenvError(f"{env.name} has prefix {env.prefix}.")
        return up(env, args.wait, args.timeout)

    # Prefixes are tried against the compose file here: the new worktree's
    # is the same, and is checked again before its stack comes up.
    here = Path(git("rev-parse", "--show-toplevel", cwd="."))
    if args.prefix is not None:
        check_prefix(args.prefix, here, envs)
        prefix = args.prefix
    else:
        prefix = free_prefix(here, envs)

    if existing is not None:
        path, branch = existing.path, existing.branch
    else:
        name = name or f"env-{prefix}"
        path = main / WORKTREES / name
        branch = args.branch or name
        if path.exists():
            raise DevenvError(f"{path} exists and isn't a worktree.")
        create_worktree(main, path, branch, args.base)

    write_prefix(path, prefix)
    return up(Env(path, branch, prefix, False), args.wait, args.timeout)


def cmd_resume(args):
    env = select(environments(main_checkout()), args.env)
    return up(env, args.wait, args.timeout)


def cmd_list(args):
    all_containers = containers()
    return [summary(env, all_containers) for env in environments(main_checkout())]


def cmd_status(args):
    env = select(environments(main_checkout()), args.env, allow_main=True)
    result = summary(env)
    result["services"] = [
        {"service": c.service, "state": c.state, "status": c.status}
        for c in containers()
        if c.project == result["project"]
    ]
    changes = git("status", "--porcelain", cwd=env.path)
    result["changed_files"] = len(changes.splitlines())
    return result


def cmd_down(args):
    main = main_checkout()
    if args.remove and args.env is None:
        raise DevenvError("Name the environment to remove.")
    env = select(environments(main), args.env)
    if args.remove and inside(Path.cwd().resolve(), env.path):
        raise DevenvError(f"Leave {env.path} before removing it.")

    note(f"Taking down {env.name}")
    stream(compose("down"), cwd=env.path, env=compose_env(env.prefix))
    result = {
        "name": env.name,
        "prefix": env.prefix,
        "path": str(env.path),
        "removed": False,
    }
    if not args.remove:
        return result

    note(f"Removing {env.path}")
    git(
        "worktree",
        "remove",
        *(["--force"] if args.force else []),
        str(env.path),
        cwd=main,
    )
    result["removed"] = True
    if env.branch:
        deleted = run(["git", "branch", "-d", env.branch], cwd=main, check=False)
        result["branch_deleted"] = deleted.returncode == 0
        if deleted.returncode != 0:
            note(f"Kept branch {env.branch}: {deleted.stderr.strip()}")
    return result


# Output


def show(command, result):
    if command == "list":
        rows = [("PREFIX", "NAME", "BRANCH", "STATUS", "APP")]
        for r in result:
            rows.append(
                (
                    str(r["prefix"] or "-"),
                    r["name"],
                    r["branch"] or "-",
                    r["status"],
                    r.get("app", "-"),
                )
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            print(
                "  ".join(
                    cell.ljust(width) for cell, width in zip(row, widths)
                ).rstrip()
            )
        return

    if command == "down":
        what = (
            "removed" if result["removed"] else "down; its data stays in the worktree"
        )
        print(f"{result['name']} is {what}.")
        return

    print(f"{result['project']} · {result['name']} ({result['status']})")
    print(f"  app       {result.get('app', '-')}   log in as {result['login']}")
    print(
        f"  minio     {result.get('minio', '-')}   console {result.get('minio_console', '-')}"
    )
    print(f"  db mcp    {result.get('mcp', '-')}")
    print(f"  worktree  {result['path']}  (branch {result['branch'] or 'detached'})")
    if command == "status":
        print(f"  changes   {result['changed_files']} changed files")
        for s in result["services"]:
            print(f"    {s['service']:<18} {s['status']}")


def parser():
    p = argparse.ArgumentParser(
        prog="devenv.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    def command(name, help):
        c = sub.add_parser(name, help=help)
        c.add_argument("--json", action="store_true", help="print the result as JSON")
        return c

    def waiting(c):
        c.add_argument(
            "--no-wait",
            dest="wait",
            action="store_false",
            help="don't wait for the app to answer",
        )
        c.add_argument(
            "--timeout",
            type=int,
            default=540,
            help="seconds to wait for it [default: 540]",
        )

    start = command("start", "create or take a worktree and bring its stack up")
    start.add_argument("name", nargs="?")
    start.add_argument("--prefix", type=int)
    start.add_argument("--branch")
    start.add_argument("--base", help="what a new branch starts from [default: HEAD]")
    waiting(start)

    command("list", "every environment and its state")

    status = command("status", "where an environment is and what runs in it")
    status.add_argument("env", nargs="?")

    resume = command("resume", "bring an environment's stack up again")
    resume.add_argument("env", nargs="?")
    waiting(resume)

    down = command("down", "stop and remove an environment's containers")
    down.add_argument("env", nargs="?")
    down.add_argument(
        "--remove", action="store_true", help="remove the worktree and its data too"
    )
    down.add_argument(
        "--force", action="store_true", help="remove it even with changes in it"
    )
    return p


COMMANDS = {
    "start": cmd_start,
    "list": cmd_list,
    "status": cmd_status,
    "resume": cmd_resume,
    "down": cmd_down,
}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = COMMANDS[args.command](args)
    except DevenvError as error:
        print(f"devenv: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        show(args.command, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
