"""Central runner CLI (``tasks-agent``): list / run / tick.

- ``list``  show registered jobs and their configured schedule
- ``run``   run a job now (draft to workdir)
- ``tick``  run every job whose cron schedule is due since its last run — the
            single crontab entry that drives everything
"""

import argparse
from datetime import datetime

from croniter import croniter

from .config.agent import AgentConfig
from .jobs import JOB_REGISTRY, build_context
from .jobs.base import JobContext


def _parse_params(pairs) -> dict:
    params = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--param expects K=V, got: {pair}")
        key, value = pair.split("=", 1)
        params[key] = value
    return params


def _is_due(cron_expr: str, last: datetime | None, now: datetime) -> bool:
    if last is None:
        return True  # never run -> due on first tick
    return croniter(cron_expr, last).get_next(datetime) <= now


def _cmd_list(args):
    cfg = AgentConfig.load()
    schedule = {e.name: e for e in cfg.schedule}
    if not JOB_REGISTRY:
        print("No jobs registered.")
        return
    for name in sorted(JOB_REGISTRY):
        entry = schedule.get(name)
        if entry:
            state = "enabled" if entry.enabled else "disabled"
            extra = f" params={entry.params}" if entry.params else ""
            print(f"{name:16} {entry.cron:16} [{state}]{extra}")
        else:
            print(f"{name:16} {'(no schedule)':16}")


def _cmd_run(args):
    job_cls = JOB_REGISTRY.get(args.name)
    if not job_cls:
        raise SystemExit(
            f"Unknown job '{args.name}'. Known: {', '.join(sorted(JOB_REGISTRY))}"
        )
    params = _parse_params(args.param)
    if args.window:
        params.setdefault("window", args.window)
    ctx = build_context(params=params)
    path = job_cls().run(ctx)
    print(f"Wrote draft: {path}")


def _cmd_tick(args):
    base = build_context()
    ran = False
    for entry in base.agent_config.schedule:
        if not entry.enabled:
            continue
        job_cls = JOB_REGISTRY.get(entry.name)
        if not job_cls:
            print(f"skip {entry.name}: no such job registered")
            continue
        if not _is_due(entry.cron, base.workdir.get_last_run(entry.name), base.now):
            continue
        ctx = JobContext(
            api=base.api,
            agent_config=base.agent_config,
            workdir=base.workdir,
            now=base.now,
            params=dict(entry.params),
        )
        path = job_cls().run(ctx)
        base.workdir.set_last_run(entry.name, base.now)
        print(f"ran {entry.name}: {path}")
        ran = True
    if not ran:
        print("nothing due")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tasks-agent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List registered jobs and their schedule")
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser("run", help="Run a job now")
    p_run.add_argument("name")
    p_run.add_argument("--param", action="append", default=[], metavar="K=V")
    p_run.add_argument("--window", choices=["daily", "weekly"])
    p_run.set_defaults(func=_cmd_run)

    p_tick = sub.add_parser("tick", help="Run jobs whose schedule is due")
    p_tick.set_defaults(func=_cmd_tick)

    args = parser.parse_args(argv)
    args.func(args)
