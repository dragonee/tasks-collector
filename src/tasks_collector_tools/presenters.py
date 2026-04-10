"""Presenter classes for tasks collector tools."""

import re
from typing import List, Type
from textwrap import dedent

from .utils import render_template
from .models import (
    BaseEvent, Habit, JournalAdded, HabitTracked, ObservationEvent,
    ObservationMade, ObservationUpdated, ObservationRecontextualized,
    ObservationReinterpreted, ObservationReflectedUpon, ObservationClosed,
    InsightRefined, ObservationAttached, ObservationDetached,
    ProjectedOutcomeMade, ProjectedOutcomeRedefined, ProjectedOutcomeRescheduled, ProjectedOutcomeMoved, ProjectedOutcomeClosed,
    Plan, Reflection, Event
)

# Parse - [x] or - [~] or - [^] or - [ ] and strip it from beginning of line
CUTREGEX = re.compile(r'^\s*\-\s*(?:\[x\^\~\s\])?\s*')

def listize(text, prefix='- ', cutregex=CUTREGEX):
    if text is None:
        return ''
    return '\n'.join(f'{prefix}{cutregex.sub("", line)}' for line in text.split('\n') if line.strip())

def first_line(text):
    splitted = text.split('\n')

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip('.…') + '…'

    return text

RE_SOMETIME = re.compile(r'\d{1,2}:\d{2}(?::\d{2})?')

DEFAULT_TIME_FORMAT = '%H:%M'

# Presenter classes for Event presentation logic
class BaseEventPresenter:
    def __init__(self, event: Event, time_format: str = DEFAULT_TIME_FORMAT):
        self.event = event
        self.time_format = time_format
    
    def nice_published(self):
        return self.event.published.strftime(self.time_format)
    
    def render(self):
        return render_template(self.get_template(), self)
    
    def get_template(self):
        return dedent(self.base_template) + '\n' + dedent(self.template)
    
    base_template: str = """
    ### {{ nice_published }}: {{ event.resourcetype }}
    """
    
    template: str = ""

class JournalAddedPresenter(BaseEventPresenter):
    base_template: str = """
    ### {{ nice_published }}
    """
    
    template: str = """    
    {{ event.comment }}
    """

    def nice_published(self):
        published_time = self.event.published.time()

        if published_time.hour == 23 and published_time.minute == 59 and published_time.second == 59:
            return 'At the end of the day...'

        if published_time.hour == 0 and published_time.minute == 0 and published_time.second == 0:
            match = RE_SOMETIME.search(self.event.comment)

            if match:
                return match.group(0)

            return 'Sometime that day...'

        return super().nice_published()

class HabitTrackedPresenter(BaseEventPresenter):
    def render(self):
        if self.event.published.strftime('%H:%M') == '00:00':
            return f'- {self.get_note()}'

        return f'- {self.nice_published()}: {self.get_note()}'

    def get_keyword(self) -> str:
        note = self.get_note()
        
        for keyword in self.event.habit.keywords:
            if re.match(r'^[!#]' + keyword, note):
                return keyword

        if len(self.event.habit.keywords) > 0:
            return self.event.habit.keywords[0]
        
        name = self.event.habit.name
        raise ValueError(f"Habit {name} has no keywords")

    def get_note(self):
        if not self.event.note:
            occured_str = '#' if self.event.occured else '!'
            keyword = self.get_keyword()

            return f'{occured_str}{keyword}'
        
        return self.event.note

class ObservationMadePresenter(BaseEventPresenter):
    template: str = """    
    {{ event.situation }}
    {% if event.interpretation %}
    ### Interpretation
    
    {{ event.interpretation }}
    {% endif %}
    {% if event.approach %}
    ### Approach

    {{ event.approach }}
    {% endif %}
    """

class ObservationUpdatedPresenter(BaseEventPresenter):
    base_template: str = """
    ### {{ nice_published }}: {{ event.resourcetype }} ({{ observation }})
    """

    template: str = """
    {% if event.situation_at_creation %}
    > {{ situation_line }}
    {% endif %}
    {{ event.comment }}
    """

    def situation_line(self):
        return first_line(self.event.situation_at_creation)

    def observation(self):
        if self.event.observation_id:
            return f'#{self.event.observation_id}'
        
        return self.event.event_stream_id

class ObservationRecontextualizedPresenter(BaseEventPresenter):
    template: str = """    
    {{ event.situation }}
    """

class ObservationReinterpretedPresenter(BaseEventPresenter):
    template: str = """
    {% if event.situation_at_creation %}
    > {{ situation_line }}
    {% endif %}
    {{ event.interpretation }}
    """

    def situation_line(self):
        return first_line(self.event.situation_at_creation)

class ObservationReflectedUponPresenter(BaseEventPresenter):
    template: str = """
    {% if event.situation_at_creation %}
    > {{ situation_line }}
    {% endif %}
    {{ event.approach }}
    """

    def situation_line(self):
        return first_line(self.event.situation_at_creation)

class ObservationClosedPresenter(BaseEventPresenter):
    template: str = """
    {{ event.situation }}

    {% if event.interpretation %}
    ### Interpretation

    {{ event.interpretation }}
    {% endif %}
    {% if event.approach %}
    ### Approach

    {{ event.approach }}
    {% endif %}
    """

class InsightRefinedPresenter(BaseEventPresenter):
    template: str = """
    {% if event.situation %}
    {{ event.situation }}
    {% endif %}
    {% if event.approach %}
    ### Approach

    {{ event.approach }}
    {% endif %}
    """

class ObservationAttachedPresenter(BaseEventPresenter):
    template: str = """
    Attached observation {{ observation_ref }} to thread {{ event.thread }}
    """

    def observation_ref(self):
        if self.event.observation:
            return f"#{self.event.observation}"
        return self.event.other_event_stream_id

class ObservationDetachedPresenter(BaseEventPresenter):
    template: str = """
    Detached observation {{ event.other_event_stream_id }} from thread {{ event.thread }}
    """

class ProjectedOutcomeMadePresenter(BaseEventPresenter):
    template: str = """
    **{{ event.name }}**
    {% if event.description %}
    
    {{ event.description }}
    {% endif %}
    {% if resolved_by_date %}
    
    *Resolve by: {{ resolved_by_date }}*
    {% endif %}
    {% if event.success_criteria %}
    
    ### Success Criteria
    {{ event.success_criteria }}
    {% endif %}
    """

    def resolved_by_date(self):
        return self.event.resolved_by.strftime('%Y-%m-%d') if self.event.resolved_by else None

class ProjectedOutcomeRedefinedPresenter(BaseEventPresenter):
    template: str = """
    {% if event.new_name %}**{{ event.new_name }}**{% endif %}{% if event.old_name %} (was: *{{ event.old_name }}*){% endif %}
    {% if event.new_description %}
    
    {{ event.new_description }}
    {% endif %}
    {% if event.new_success_criteria %}
    
    ### Success Criteria
    {{ event.new_success_criteria }}
    {% endif %}
    """

class ProjectedOutcomeRescheduledPresenter(BaseEventPresenter):
    template: str = """
    Rescheduled{% if old_resolved_by_date and new_resolved_by_date %} from {{ old_resolved_by_date }} to {{ new_resolved_by_date }}{% elif new_resolved_by_date %} to {{ new_resolved_by_date }}{% elif old_resolved_by_date %} (was {{ old_resolved_by_date }}){% endif %}
    """

    def old_resolved_by_date(self):
        return self.event.old_resolved_by.strftime('%Y-%m-%d') if self.event.old_resolved_by else None

    def new_resolved_by_date(self):
        return self.event.new_resolved_by.strftime('%Y-%m-%d') if self.event.new_resolved_by else None

class ProjectedOutcomeMovedPresenter(BaseEventPresenter):
    template: str = """
    **{{ event.name }}** moved{% if event.old_breakthrough and event.new_breakthrough %} from *{{ event.old_breakthrough }}* to *{{ event.new_breakthrough }}*{% elif event.new_breakthrough %} to *{{ event.new_breakthrough }}*{% endif %}
    {% if event.description %}

    {{ event.description }}
    {% endif %}
    """

class ProjectedOutcomeClosedPresenter(BaseEventPresenter):
    template: str = """
    **{{ event.name }}** ✓
    {% if event.description %}
    
    {{ event.description }}
    {% endif %}
    {% if event.success_criteria %}
    
    ### Success Criteria
    {{ event.success_criteria }}
    {% endif %}
    """

# Presenter classes for Plan and Reflection
class BaseModelPresenter:
    def __init__(self, model):
        self.model = model

class PlanPresenter(BaseModelPresenter):
    def focus_list(self, prefix='- '):
        return listize(self.model.focus, prefix=prefix)

class ReflectionPresenter(BaseModelPresenter):
    def good_list(self, prefix='- '):
        return listize(self.model.good, prefix=prefix)
    
    def better_list(self, prefix='- '):
        return listize(self.model.better, prefix=prefix)
    
    def best_list(self, prefix='- '):
        return listize(self.model.best, prefix=prefix)

# Presenter factory functions
def get_presenter_class(event: Event):
    match event:
        case JournalAdded():
            return JournalAddedPresenter
        case HabitTracked():
            return HabitTrackedPresenter
        case ObservationMade():
            return ObservationMadePresenter
        case ObservationUpdated():
            return ObservationUpdatedPresenter
        case ObservationRecontextualized():
            return ObservationRecontextualizedPresenter
        case ObservationReinterpreted():
            return ObservationReinterpretedPresenter
        case ObservationReflectedUpon():
            return ObservationReflectedUponPresenter
        case ObservationClosed():
            return ObservationClosedPresenter
        case InsightRefined():
            return InsightRefinedPresenter
        case ObservationAttached():
            return ObservationAttachedPresenter
        case ObservationDetached():
            return ObservationDetachedPresenter
        case ProjectedOutcomeMade():
            return ProjectedOutcomeMadePresenter
        case ProjectedOutcomeRedefined():
            return ProjectedOutcomeRedefinedPresenter
        case ProjectedOutcomeRescheduled():
            return ProjectedOutcomeRescheduledPresenter
        case ProjectedOutcomeMoved():
            return ProjectedOutcomeMovedPresenter
        case ProjectedOutcomeClosed():
            return ProjectedOutcomeClosedPresenter
        case _:
            return BaseEventPresenter

def get_presenter(event: Event, time_format: str = DEFAULT_TIME_FORMAT) -> BaseEventPresenter:
    presenter_class = get_presenter_class(event)
    return presenter_class(event, time_format=time_format)

def get_plan_presenter(plan: Plan) -> PlanPresenter:
    return PlanPresenter(plan)

def get_reflection_presenter(reflection: Reflection) -> ReflectionPresenter:
    return ReflectionPresenter(reflection) 