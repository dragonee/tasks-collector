from django.contrib import admin
from .models import Board, BoardCommitted, Thread, Plan, Reflection, Observation, ObservationType, Habit, HabitTracked, ObservationUpdated, JournalAdded, Event, ObservationMade, ObservationRecontextualized, ObservationReinterpreted, ObservationReflectedUpon, ObservationClosed

from datetime import datetime

from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin

from django.db import transaction


class ObservationTypeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

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
    ]

    ordering = ['-published', '-pk']

class HabitTrackedAdmin(PolymorphicChildModelAdmin):
    base_model = HabitTracked

class ObservationUpdatedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationUpdated

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
admin.site.register(Habit)
admin.site.register(HabitTracked, HabitTrackedAdmin)
admin.site.register(ObservationUpdated, ObservationUpdatedAdmin)
admin.site.register(JournalAdded, JournalAddedAdmin)
admin.site.register(Event, EventAdmin)
