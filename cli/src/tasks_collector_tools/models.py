"""Pydantic models for tasks collector tools."""

from datetime import datetime, date
from typing import List, Optional, Literal, Union
from pydantic import BaseModel


def not_empty(text):
    return text and text.strip() != '' and text.strip() != '?'


class BaseEvent(BaseModel):
    id: int
    published: datetime
    resourcetype: str


class Habit(BaseModel):
    id: int
    name: str
    description: Optional[str]
    slug: str
    keywords: List[str]


class HabitWithTracked(Habit):
    today_tracked: int


class Keyword(BaseModel):
    id: int
    keyword: str
    habit: Habit

class JournalAdded(BaseEvent):
    resourcetype: Literal['JournalAdded']
    comment: str
    tags: List[str]


class PhotoAdded(JournalAdded):
    resourcetype: Literal['PhotoAdded']


class HabitTracked(BaseEvent):
    resourcetype: Literal['HabitTracked']
    note: str
    occured: bool
    habit: Habit


class ObservationEvent(BaseEvent):
    event_stream_id: str

class ObservationMade(ObservationEvent):
    url: str
    resourcetype: Literal['ObservationMade']
    type: str
    situation: str
    interpretation: Optional[str]
    approach: Optional[str]


class ObservationUpdated(ObservationEvent):
    url: str
    resourcetype: Literal['ObservationUpdated']
    observation_id: Optional[int]
    situation_at_creation: str
    comment: str


class ObservationRecontextualized(ObservationEvent):
    url: str
    resourcetype: Literal['ObservationRecontextualized']
    situation: str
    old_situation: str


class ObservationReinterpreted(ObservationEvent):
    url: str
    resourcetype: Literal['ObservationReinterpreted']
    interpretation: Optional[str]
    old_interpretation: Optional[str]
    situation_at_creation: str


class ObservationReflectedUpon(ObservationEvent):
    url: str
    resourcetype: Literal['ObservationReflectedUpon']
    approach: Optional[str]
    old_approach: Optional[str]
    situation_at_creation: str


class ObservationClosed(ObservationEvent):
    url: str
    resourcetype: Literal['ObservationClosed']
    type: str
    situation: str
    interpretation: Optional[str]
    approach: Optional[str]


class InsightRefined(ObservationEvent):
    url: str
    resourcetype: Literal['InsightRefined']
    type: str
    situation: Optional[str]
    approach: Optional[str]


class ObservationAttached(BaseEvent):
    resourcetype: Literal['ObservationAttached']
    other_event_stream_id: str
    observation: Optional[int]


class ObservationDetached(BaseEvent):
    resourcetype: Literal['ObservationDetached']
    other_event_stream_id: str


class ProjectedOutcomeMade(BaseEvent):
    resourcetype: Literal['ProjectedOutcomeMade']
    event_stream_id: str
    thread: str
    name: str
    description: Optional[str]
    resolved_by: Optional[datetime]
    success_criteria: Optional[str]


class ProjectedOutcomeRedefined(BaseEvent):
    resourcetype: Literal['ProjectedOutcomeRedefined']
    event_stream_id: str
    thread: str
    old_name: Optional[str]
    new_name: Optional[str]
    old_description: Optional[str]
    new_description: Optional[str]
    old_success_criteria: Optional[str]
    new_success_criteria: Optional[str]


class ProjectedOutcomeRescheduled(BaseEvent):
    resourcetype: Literal['ProjectedOutcomeRescheduled']
    event_stream_id: str
    thread: str
    old_resolved_by: Optional[datetime]
    new_resolved_by: Optional[datetime]


class ProjectedOutcomeMoved(BaseEvent):
    resourcetype: Literal['ProjectedOutcomeMoved']
    event_stream_id: str
    thread: str
    name: str
    description: Optional[str]
    resolved_by: Optional[datetime]
    confidence_level: Optional[str]
    old_breakthrough: Optional[int]
    new_breakthrough: Optional[int]


class ProjectedOutcomeClosed(BaseEvent):
    resourcetype: Literal['ProjectedOutcomeClosed']
    event_stream_id: str
    thread: str
    name: str
    description: Optional[str]
    resolved_by: Optional[datetime]
    success_criteria: Optional[str]


class ProjectedOutcomeEvolved(BaseEvent):
    resourcetype: Literal['ProjectedOutcomeEvolved']
    event_stream_id: str
    thread: str
    note: str


class Plan(BaseModel):
    id: int
    focus: str|None
    pub_date: date

    def empty(self):
        return not self.has_focus()

    def has_focus(self):
        return not_empty(self.focus)


class Reflection(BaseModel):
    id: int
    good: str
    better: Optional[str]
    best: Optional[str]
    pub_date: date

    def empty(self):
        return not self.has_good() and not self.has_better() and not self.has_best()

    def has_good(self):
        return not_empty(self.good)
    
    def has_better(self):
        return not_empty(self.better)
    
    def has_best(self):
        return not_empty(self.best)


Event = Union[
    PhotoAdded,
    JournalAdded,
    HabitTracked,
    ObservationMade, 
    ObservationUpdated, 
    ObservationRecontextualized, 
    ObservationReinterpreted, 
    ObservationReflectedUpon, 
    ObservationClosed,
    InsightRefined,
    ObservationAttached,
    ObservationDetached,
    ProjectedOutcomeMade,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
    ProjectedOutcomeMoved,
    ProjectedOutcomeClosed,
    ProjectedOutcomeEvolved
]

class DefaultBoardThread(BaseModel):
    id: int
    name: str


class Profile(BaseModel):
    id: int
    default_board_thread: DefaultBoardThread


class ProfileResponse(BaseModel):
    count: int
    results: List[Profile]


class Result(BaseModel):
    date: date
    events: List[Event]
    plan: Optional[Plan]
    reflection: Optional[Reflection]

    def empty(self):
        if self.events:
            return False

        if self.plan and not self.plan.empty():
            return False

        if self.reflection and not self.reflection.empty():
            return False

        return True


class StatsResponse(BaseModel):
    year: Optional[int]
    years: List[int]
    journal_count: int
    habit_count: int
    observation_count: int
    observation_updated_count: int
    observation_closed_count: int
    event_count: int
    observation_recontextualized_count: int
    observation_reflected_upon_count: int
    observation_reinterpreted_count: int
    projected_outcome_made_count: int
    projected_outcome_redefined_count: int
    projected_outcome_rescheduled_count: int
    projected_outcome_closed_count: int
    word_count: int
    word_count_updated: datetime 