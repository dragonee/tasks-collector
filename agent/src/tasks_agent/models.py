"""Pydantic v2 response models for the reads the jobs need.

Events are modelled permissively: a single ``Event`` type with ``extra="allow"``
carries the fields common across the backend's polymorphic event feed, keyed by
``resourcetype``. This means any event type round-trips without a bespoke
subclass, which is what a read-mostly agent wants.
"""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

OBSERVATION_EVENT_TYPES = frozenset(
    {
        "ObservationMade",
        "ObservationUpdated",
        "ObservationRecontextualized",
        "ObservationReinterpreted",
        "ObservationReflectedUpon",
        "ObservationClosed",
        "InsightRefined",
        "ObservationAttached",
        "ObservationDetached",
    }
)
JOURNAL_EVENT_TYPES = frozenset({"JournalAdded", "PhotoAdded"})


def not_empty(text: Optional[str]) -> bool:
    return bool(text and text.strip() not in ("", "?"))


class Event(BaseModel):
    model_config = ConfigDict(extra="allow")

    published: datetime
    resourcetype: str

    # Fields that appear across event subtypes (all optional).
    comment: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    occured: Optional[bool] = None
    habit: Optional[dict[str, Any]] = None
    event_stream_id: Optional[str] = None
    situation: Optional[str] = None
    situation_at_creation: Optional[str] = None
    url: Optional[str] = None

    @property
    def is_journal(self) -> bool:
        return self.resourcetype in JOURNAL_EVENT_TYPES

    @property
    def is_habit(self) -> bool:
        return self.resourcetype == "HabitTracked"

    @property
    def is_observation(self) -> bool:
        return self.resourcetype in OBSERVATION_EVENT_TYPES

    @property
    def habit_name(self) -> str:
        return (self.habit or {}).get("name", "?")

    def best_situation(self) -> Optional[str]:
        """The situation text an observation event carries, however it's named."""
        return self.situation or self.situation_at_creation


class Plan(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[int] = None
    focus: Optional[str] = None
    pub_date: Optional[date] = None

    def has_focus(self) -> bool:
        return not_empty(self.focus)


class Reflection(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[int] = None
    good: Optional[str] = None
    better: Optional[str] = None
    best: Optional[str] = None
    pub_date: Optional[date] = None

    def has_good(self) -> bool:
        return not_empty(self.good)

    def has_better(self) -> bool:
        return not_empty(self.better)

    def has_best(self) -> bool:
        return not_empty(self.best)

    def empty(self) -> bool:
        return not (self.has_good() or self.has_better() or self.has_best())


class DailyResult(BaseModel):
    """Response shape of ``GET /api/events/daily/``."""

    date: date
    events: list[Event] = Field(default_factory=list)
    plan: Optional[Plan] = None
    reflection: Optional[Reflection] = None

    @classmethod
    def parse(cls, data: dict) -> "DailyResult":
        return cls.model_validate(data)

    def empty(self) -> bool:
        if self.events:
            return False
        if self.plan and self.plan.has_focus():
            return False
        if self.reflection and not self.reflection.empty():
            return False
        return True

    def journals(self) -> list[Event]:
        return [e for e in self.events if e.is_journal]

    def habits(self) -> list[Event]:
        return [e for e in self.events if e.is_habit]

    def observations(self) -> list[Event]:
        return [e for e in self.events if e.is_observation]
