from django.contrib import admin
from .models import Board, Thread, Plan, Reflection, Observation, ObservationType, Update

from datetime import datetime

# Register your models here.

class ObservationTypeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

@admin.action(description='Close selected observations')
def close_observations(modeladmin, request, queryset):
    queryset.update(date_closed=datetime.today())


class UpdateInline(admin.StackedInline):
    model = Update

    readonly_fields = ('pub_date',)

class ObservationAdmin(admin.ModelAdmin):
    list_filter = ('date_closed',)

    list_display = ('__str__', 'date_closed', 'thread', 'type')

    actions = [close_observations]

    inlines = [
        UpdateInline
    ]

admin.site.register(Board)
admin.site.register(Thread)
admin.site.register(Plan)
admin.site.register(Reflection)
admin.site.register(Observation, ObservationAdmin)
admin.site.register(ObservationType, ObservationTypeAdmin)

