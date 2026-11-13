"""The daily/weekly review job.

Reads the backend day-by-day over the window (``GET /api/events/daily/`` returns
journals, habits, observations, plan and reflection for each day), renders the
material into Markdown context, asks the DSPy review program to write a review,
and drafts it to the workdir. It does NOT post anything back to the backend.
"""

import argparse
from datetime import timedelta

import dspy

from ..api import ApiError
from ..llm import build_lm
from ..models import DailyResult
from ..programs.review import ReviewProgram
from .base import Job, JobContext, build_context, register


def _daterange(since, until):
    day = since
    while day <= until:
        yield day
        day += timedelta(days=1)


def _first_line(text: str) -> str:
    lines = text.strip().split("\n")
    first = lines[0].rstrip()
    if len(lines) > 1:
        return first.rstrip(".…") + "…"
    return first


@register
class ReviewJob(Job):
    name = "review"

    def run(self, ctx: JobContext):
        window = ctx.params.get("window", "weekly")
        until = ctx.now.date()
        since = until - timedelta(days=6) if window == "weekly" else until

        results = []
        for day in _daterange(since, until):
            result = DailyResult.parse(ctx.api.daily(day.isoformat()))
            if not result.empty():
                results.append(result)

        journal_entries = self._render_journals(results)
        events = self._render_events(results)
        plans = self._render_plans(ctx, until)
        guidance = ctx.workdir.read_context("style.md", "persona.md")
        period = self._period(since, until, window)

        program = ReviewProgram()
        with dspy.context(lm=build_lm(self.name, ctx.agent_config)):
            pred = program(
                window=window,
                period=period,
                journal_entries=journal_entries or "(no journal entries)",
                events=events or "(no tracked events)",
                plans=plans or "(no active plans)",
                guidance=guidance,
            )

        spec = ctx.agent_config.model_for(self.name)
        meta = {
            "job": self.name,
            "window": window,
            "period": period,
            "model": spec.model,
            "generated_at": ctx.now.isoformat(timespec="seconds"),
            "source_days": len(results),
            "journal_count": sum(len(r.journals()) for r in results),
            "habit_count": sum(len(r.habits()) for r in results),
            "observation_event_count": sum(len(r.observations()) for r in results),
        }

        name = f"{until.isoformat()}-{window}-review.md"
        path = ctx.workdir.write_draft(self.name, name, self._draft(meta, pred.review))
        ctx.workdir.write_run_log(self.name, {**meta, "draft": str(path)}, ctx.now)
        return path

    # ---- context rendering ----
    def _render_journals(self, results) -> str:
        blocks = []
        for r in results:
            for e in r.journals():
                if not e.comment:
                    continue
                tags = f" [{', '.join(e.tags)}]" if e.tags else ""
                blocks.append(f"### {r.date.isoformat()}{tags}\n\n{e.comment.strip()}")
        return "\n\n".join(blocks)

    def _render_events(self, results) -> str:
        lines = []
        for r in results:
            habits, observations = r.habits(), r.observations()
            if not habits and not observations:
                continue
            lines.append(f"### {r.date.isoformat()}")
            for h in habits:
                mark = {True: " (done)", False: " (missed)"}.get(h.occured, "")
                note = f" — {h.note.strip()}" if h.note else ""
                lines.append(f"- Habit: {h.habit_name}{mark}{note}")
            seen: dict[str, str] = {}
            for o in observations:
                situation = o.best_situation()
                key = o.event_stream_id or situation
                if situation and key not in seen:
                    seen[key] = _first_line(situation)
            for situation in seen.values():
                lines.append(f"- Observation: {situation}")
        return "\n".join(lines)

    def _render_plans(self, ctx: JobContext, until) -> str:
        try:
            data = ctx.api.plans_today(until.isoformat())
        except ApiError:
            return ""
        sections = []
        for key in ("daily", "weekly", "monthly"):
            plan = data.get(key)
            if not plan:
                continue
            tasks = plan.get("tasks") or []
            if not tasks:
                continue
            block = [f"### {plan.get('thread', key.title())}"]
            for t in tasks:
                box = "[x]" if t.get("done") else "[ ]"
                block.append(f"- {box} {(t.get('text') or '').strip()}")
            sections.append("\n".join(block))
        return "\n\n".join(sections)

    def _period(self, since, until, window) -> str:
        if window == "daily" or since == until:
            return until.strftime("%A, %B %-d, %Y")
        return f"{since.strftime('%B %-d')} – {until.strftime('%B %-d, %Y')}"

    def _draft(self, meta: dict, review: str) -> str:
        front_keys = (
            "generated_at",
            "window",
            "period",
            "model",
            "source_days",
            "journal_count",
            "habit_count",
            "observation_event_count",
        )
        front = "\n".join(f"{k}: {meta[k]}" for k in front_keys)
        heading = f"{meta['window'].title()} review — {meta['period']}"
        return f"---\n{front}\n---\n\n# {heading}\n\n{review.strip()}\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tasks-agent-review", description="Draft a daily/weekly review."
    )
    parser.add_argument("--window", choices=["daily", "weekly"], default="weekly")
    args = parser.parse_args(argv)

    ctx = build_context(params={"window": args.window})
    path = ReviewJob().run(ctx)
    print(f"Wrote draft: {path}")
