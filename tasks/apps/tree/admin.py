from django.contrib import admin

from .models import Board, BoardCommitted, Thread, Plan, Reflection, Observation, ObservationType, Habit, HabitTracked, ObservationUpdated, JournalAdded, Event

from datetime import datetime

from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin

# Register your models here.

class ObservationTypeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

@admin.action(description='Close selected observations')
def close_observations(modeladmin, request, queryset):
    queryset.update(date_closed=datetime.today())


class ObservationUpdatedInline(admin.StackedInline):
    model = ObservationUpdated

    fields = ('published', 'comment')
    readonly_fields = ('published',)

class ObservationAdmin(admin.ModelAdmin):
    list_filter = ('date_closed',)

    list_display = ('__str__', 'date_closed', 'thread', 'type')

    actions = [close_observations]

    inlines = [
        ObservationUpdatedInline
    ]

class JournalAddedAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'thread', 'published')

class EventAdmin(PolymorphicParentModelAdmin):
    base_model = Event

    list_display = ('__str__', 'published', 'thread')

    child_models = [
        HabitTracked,
        BoardCommitted,
        ObservationUpdated
    ]

class HabitTrackedAdmin(PolymorphicChildModelAdmin):
    base_model = HabitTracked

class ObservationUpdatedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationUpdated

class BoardCommittedAdmin(PolymorphicChildModelAdmin):
    base_model = BoardCommitted

admin.site.register(Board)
admin.site.register(Thread)
admin.site.register(Plan)
admin.site.register(Reflection)
admin.site.register(Observation, ObservationAdmin)
admin.site.register(ObservationType, ObservationTypeAdmin)
admin.site.register(BoardCommitted, BoardCommittedAdmin)
admin.site.register(Habit)
admin.site.register(HabitTracked, HabitTrackedAdmin)
admin.site.register(ObservationUpdated, ObservationUpdatedAdmin)
admin.site.register(ObservationUpdated)
admin.site.register(JournalAdded, JournalAddedAdmin)
admin.site.register(Event, EventAdmin)
