from django.contrib import admin
from .models import *

from datetime import datetime

from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin

from django.db import transaction


class ObservationTypeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}


class HabitAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'tagname', 'event_stream_id')

class ThreadAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('name', )
        
        return self.readonly_fields


@admin.action(description='Close selected observations')
def close_observations(modeladmin, request, queryset):
    for observation in queryset:

        observation_closed = ObservationClosed.from_observation(observation)

        with transaction.atomic():
            observation_closed.save()

            observation.delete()

class ObservationUpdatedInline(admin.StackedInline):
    model = ObservationUpdated

    fields = ('published', 'comment')
    readonly_fields = ('published',)

class ObservationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'thread', 'type')
    readonly_fields = ('event_stream_id',)

    actions = [close_observations]

    inlines = [
        ObservationUpdatedInline
    ]

class EventAdmin(PolymorphicParentModelAdmin):
    base_model = Event

    list_display = ('__str__', 'published', 'thread', 'event_stream_id')

    child_models = [
        HabitTracked,
        BoardCommitted,
        ObservationUpdated,
        ObservationMade,
        ObservationClosed,
        ObservationRecontextualized,
        ObservationReflectedUpon,
        ObservationReinterpreted,
        JournalAdded,
        ProjectedOutcomeMade,
        ProjectedOutcomeRedefined,
        ProjectedOutcomeRescheduled,
        ProjectedOutcomeClosed,
    ]

    ordering = ['-published', '-pk']

class HabitTrackedAdmin(PolymorphicChildModelAdmin):
    base_model = HabitTracked

class ObservationUpdatedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationUpdated

    list_display = ('__str__', 'event_stream_id', 'published')

class BoardCommittedAdmin(PolymorphicChildModelAdmin):
    base_model = BoardCommitted
    list_display = ('__str__', 'event_stream_id',)


class ObservationMadeAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationMade

class ObservationRecontextualizedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationRecontextualized

class ObservationReinterpretedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationReinterpreted

class ObservationReflectedUponAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationReflectedUpon

class ObservationClosedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationClosed

class JournalAddedAdmin(PolymorphicChildModelAdmin):
    base_model = JournalAdded
    
    list_display = ('__str__', 'thread', 'published')


class ProjectedOutcomeMadeAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeMade
    
    list_display = ('__str__', 'projected_outcome', 'name', 'resolved_by', 'published')
    list_filter = ('resolved_by', 'published')
    search_fields = ('name', 'description')
    readonly_fields = ('event_stream_id', 'published')


class ProjectedOutcomeRedefinedAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeRedefined
    
    list_display = ('__str__', 'projected_outcome', 'published')
    list_filter = ('published',)
    readonly_fields = ('event_stream_id', 'published')


class ProjectedOutcomeRescheduledAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeRescheduled
    
    list_display = ('__str__', 'projected_outcome', 'old_resolved_by', 'new_resolved_by', 'published')
    list_filter = ('old_resolved_by', 'new_resolved_by', 'published')
    readonly_fields = ('event_stream_id', 'published')


class ProjectedOutcomeClosedAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeClosed
    
    list_display = ('__str__', 'projected_outcome', 'name', 'resolved_by', 'published')
    list_filter = ('resolved_by', 'published')
    search_fields = ('name', 'description')
    readonly_fields = ('event_stream_id', 'published')


class ProjectedOutcomeAdmin(admin.ModelAdmin):
    list_display = ('name', 'breakthrough', 'resolved_by', 'confidence_level', 'published')
    list_filter = ('resolved_by', 'published', 'breakthrough')
    search_fields = ('name', 'description')
    readonly_fields = ('event_stream_id', 'published')


class BreakthroughAdmin(admin.ModelAdmin):
    list_display = ('slug', 'theme', 'published')
    list_filter = ('published',)
    search_fields = ('slug', 'theme', 'areas_of_concern')
    readonly_fields = ('published',)


class JournalTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')

    prepopulated_fields = {"slug": ("name",)}


admin.site.register(Board)
admin.site.register(Thread, ThreadAdmin)
admin.site.register(Plan)
admin.site.register(Reflection)
admin.site.register(Observation, ObservationAdmin)
admin.site.register(ObservationType, ObservationTypeAdmin)
admin.site.register(ObservationMade, ObservationMadeAdmin)
admin.site.register(ObservationRecontextualized, ObservationRecontextualizedAdmin)
admin.site.register(ObservationReinterpreted, ObservationReinterpretedAdmin)
admin.site.register(ObservationReflectedUpon, ObservationReflectedUponAdmin)
admin.site.register(ObservationClosed, ObservationClosedAdmin)
admin.site.register(BoardCommitted, BoardCommittedAdmin)
admin.site.register(Habit, HabitAdmin)
admin.site.register(HabitTracked, HabitTrackedAdmin)
admin.site.register(ObservationUpdated, ObservationUpdatedAdmin)
admin.site.register(JournalAdded, JournalAddedAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(QuickNote)
admin.site.register(JournalTag, JournalTagAdmin)
admin.site.register(Breakthrough, BreakthroughAdmin)
admin.site.register(ProjectedOutcome, ProjectedOutcomeAdmin)
admin.site.register(ProjectedOutcomeMade, ProjectedOutcomeMadeAdmin)
admin.site.register(ProjectedOutcomeRedefined, ProjectedOutcomeRedefinedAdmin)
admin.site.register(ProjectedOutcomeRescheduled, ProjectedOutcomeRescheduledAdmin)
admin.site.register(ProjectedOutcomeClosed, ProjectedOutcomeClosedAdmin)
