"""DSPy program for the daily/weekly review generator.

Pure LLM logic — no HTTP, no config. The job layer feeds it pre-rendered context
strings and applies the per-task LM via ``dspy.context``.
"""

import dspy


class ReviewSignature(dspy.Signature):
    """Write a warm, honest, first-person review of the given period.

    Ground every claim in the provided journal entries, events and plans — do not
    invent facts. Note progress against the plans, call out recurring themes, and
    end with one concrete, kind suggestion for the next period. Write in Markdown.
    """

    window: str = dspy.InputField(desc="'daily' or 'weekly'")
    period: str = dspy.InputField(
        desc="human date range, e.g. 'June 30 – July 6, 2026'"
    )
    journal_entries: str = dspy.InputField(desc="dated journal entries, markdown")
    events: str = dspy.InputField(
        desc="habits tracked and observations worked on, per day"
    )
    plans: str = dspy.InputField(desc="active plans with done/undone tasks")
    guidance: str = dspy.InputField(
        desc="optional tone/persona notes from the user; may be empty"
    )
    review: str = dspy.OutputField(desc="the finished review, markdown")


class ReviewProgram(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(ReviewSignature)

    def forward(self, *, window, period, journal_entries, events, plans, guidance=""):
        return self.generate(
            window=window,
            period=period,
            journal_entries=journal_entries,
            events=events,
            plans=plans,
            guidance=guidance,
        )
