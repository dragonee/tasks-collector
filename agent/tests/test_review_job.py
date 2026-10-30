import json
from datetime import datetime

import tasks_agent.jobs.review as review_mod
from dspy.utils.dummies import DummyLM
from tasks_agent.config.agent import AgentConfig
from tasks_agent.jobs.base import JobContext
from tasks_agent.jobs.review import ReviewJob
from tasks_agent.workdir import Workdir

DAILY = {
    "2026-07-05": {
        "date": "2026-07-05",
        "events": [
            {
                "id": 1,
                "resourcetype": "JournalAdded",
                "published": "2026-07-05T10:00:00+00:00",
                "comment": "Built the agent scaffolding.",
                "tags": ["work"],
            },
            {
                "id": 2,
                "resourcetype": "HabitTracked",
                "published": "2026-07-05T11:00:00+00:00",
                "note": "morning run",
                "occured": True,
                "habit": {"name": "Exercise"},
            },
            {
                "id": 3,
                "resourcetype": "ObservationMade",
                "published": "2026-07-05T12:00:00+00:00",
                "event_stream_id": "abc",
                "situation": "I procrastinate on hard tasks.\nMore detail here.",
                "url": "/observation/abc",
            },
        ],
        "plan": {"id": 1, "pub_date": "2026-07-05", "focus": "Ship the agent"},
        "reflection": None,
    }
}

PLANS = {
    "daily": {
        "thread": "Daily",
        "pub_date": "2026-07-07",
        "tasks": [{"text": "ship agent", "done": False}],
    },
    "weekly": None,
    "monthly": None,
}


class FakeApi:
    def daily(self, day, thread="Daily"):
        return DAILY.get(
            day, {"date": day, "events": [], "plan": None, "reflection": None}
        )

    def plans_today(self, day):
        return PLANS


def test_review_job_writes_draft(monkeypatch, tmp_path):
    lm = DummyLM([{"reasoning": "r", "review": "You built the agent this week."}])
    monkeypatch.setattr(review_mod, "build_lm", lambda name, cfg: lm)

    cfg = AgentConfig(
        {
            "agent": {"workdir": str(tmp_path)},
            "models": {"review": {"model": "test-model"}},
        }
    )
    ctx = JobContext(
        api=FakeApi(),
        agent_config=cfg,
        workdir=Workdir(cfg.workdir),
        now=datetime(2026, 7, 7, 9, 0, 0),
        params={"window": "weekly"},
    )

    path = ReviewJob().run(ctx)

    assert path.name == "2026-07-07-weekly-review.md"
    text = path.read_text()
    # LLM output
    assert "You built the agent this week." in text
    # front matter
    assert "window: weekly" in text
    assert "model: test-model" in text
    assert "journal_count: 1" in text
    assert "habit_count: 1" in text
    assert "observation_event_count: 1" in text
    assert "source_days: 1" in text

    # run log written
    runs = list((tmp_path / "runs").glob("*-review.json"))
    assert len(runs) == 1
    meta = json.loads(runs[0].read_text())
    assert meta["job"] == "review"
    assert meta["draft"] == str(path)

    # jobs draft only -- they must not touch last_run (that's the runner's job)
    assert not (tmp_path / "state" / "last_run.json").exists()


def test_review_context_rendering(monkeypatch, tmp_path):
    """The prompt strings fed to the program reflect the API data."""
    captured = {}

    class SpyProgram:
        def __call__(self, **kwargs):
            captured.update(kwargs)

            class _P:
                review = "ok"

            return _P()

    monkeypatch.setattr(review_mod, "build_lm", lambda name, cfg: DummyLM([{}]))
    monkeypatch.setattr(review_mod, "ReviewProgram", lambda: SpyProgram())

    cfg = AgentConfig({"agent": {"workdir": str(tmp_path)}})
    ctx = JobContext(
        api=FakeApi(),
        agent_config=cfg,
        workdir=Workdir(cfg.workdir),
        now=datetime(2026, 7, 7, 9, 0, 0),
        params={"window": "weekly"},
    )

    ReviewJob().run(ctx)

    assert "Built the agent scaffolding." in captured["journal_entries"]
    assert "Habit: Exercise (done)" in captured["events"]
    assert "Observation: I procrastinate on hard tasks…" in captured["events"]
    assert "[ ] ship agent" in captured["plans"]
    assert captured["period"] == "July 1 – July 7, 2026"
