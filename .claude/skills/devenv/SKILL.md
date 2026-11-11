---
name: devenv
description: Start, list, check, resume or take down a development environment of this project, a git worktree under .claude/worktrees with its own Docker Compose stack, database and ports (prefix 4 serves the app on localhost:4000), and move the session into it. Use when the user asks for a new environment or worktree to work on something in parallel, to go back to one (also after /clear), to see which are running, or to stop or remove one.
argument-hint: "[start|list|status|resume|down] [name, prefix or what it is for]"
---

# Development environments

`docker/development/devenv.py` runs them; this command calls it and moves the
session into the environment's worktree with EnterWorktree.

An environment is a worktree whose `docker/development/.env` sets
`TASKS_PORT_PREFIX`. Prefix 4 is the compose project `tasks-4`: the app on
http://localhost:4000, MinIO on 4900 (console 4901), the database MCP on 4079.
Its database is its own, seeded on the first start: log in as django / django;
alice / django has a board and an observation shared with her. The main
checkout has no prefix and keeps 8000, 9000, 9001 and 7079.

## 1. Read the request

Turn the user's words into one devenv command:

| They say | Run |
| --- | --- |
| nothing, "list", "what's running" | `list` |
| "start trip-photos", "a new env for the trip photos" | `start trip-photos` |
| "new one on 6 for the habits page", "on 6xxx" | `start habits-page --prefix 6` |
| "for branch feat/sharing" | `start --branch feat/sharing` |
| "resume", "back to 4", "back to the trip photos one" | `resume`, `resume 4`, `resume trip-photos` |
| "status", "is 4 up?" | `status`, `status 4` |
| "stop 4", "down", "shut it down" | `down 4`, `down` |
| "remove 4", "delete trip-photos and its worktree" | `down 4 --remove` |

- A name for `start` is short kebab-case made from what the user said it is
  for: letters, digits, `.`, `_`, `-`, and not only digits (a number is a
  prefix). Without anything to name it after, leave the name out: it becomes
  `env-<prefix>`.
- An environment (ENV) is a prefix, a worktree name, a branch or a path. Left
  out, it is the one the session is in, or the only one there is. To go back
  to one whose name the user describes loosely, run `list` first and pick it.
- Don't ask the user anything unless two environments fit what they said.

## 2. Run it

Run it from the current directory with Bash and a 600000 ms timeout:

```
python3 docker/development/devenv.py <command> [args]
```

`start` and `resume` wait until the app answers and the frontend is built. A
new environment installs packages, migrates and seeds first, which takes a few
minutes. If it ends with "Not ready after", run `resume` with that environment
to wait again; if a container stopped, show the user the log lines it printed.

### start and resume

Add `--json`. The JSON on stdout has `path`, `prefix`, `project`, `branch`,
`app` and `login`. Then call **EnterWorktree with `path`**. Do this every time,
even if the session seems to be there already: after /clear it may not be.

Tell the user the app URL, the login, the branch and the worktree. Commands
from CLAUDE.md now reach this environment's stack as they are written, run
from the worktree.

### down

`down` stops and removes the containers; the data stays in the worktree and
`resume` brings it back. With `--remove`:

1. If the session is in that environment's worktree, call **ExitWorktree with
   `action: "keep"`** first. devenv refuses to remove the directory the
   session is in, and ExitWorktree never removes a worktree entered by path.
2. Run `down <ENV> --remove`. It removes the worktree with its database, and
   deletes the branch only if it is merged.
3. If git refuses because the worktree has changes, tell the user what it
   said. Add `--force` only when they say so: it throws the changes away.

### list and status

Run them as they are and show the output.
