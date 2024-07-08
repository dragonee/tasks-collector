from django.contrib import admin
from .models import Board, BoardCommitted, Thread, Plan, Reflection, Observation, ObservationType, Habit, HabitTracked, EditableHabitsLine, ObservationUpdated, JournalAdded

from datetime import datetime

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


admin.site.register(Board)
admin.site.register(Thread)
admin.site.register(Plan)
admin.site.register(Reflection)
admin.site.register(Observation, ObservationAdmin)
admin.site.register(ObservationType, ObservationTypeAdmin)
admin.site.register(BoardCommitted)
admin.site.register(Habit)
admin.site.register(HabitTracked)
admin.site.register(EditableHabitsLine)
admin.site.register(ObservationUpdated)
admin.site.register(JournalAdded, JournalAddedAdmin)
