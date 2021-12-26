from django.contrib import admin
from .models import Board, Thread, Plan, Reflection, Observation, ObservationType

# Register your models here.

class ObservationTypeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

class ObservationAdmin(admin.ModelAdmin):
    list_filter = ('date_closed',)

admin.site.register(Board)
admin.site.register(Thread)
admin.site.register(Plan)
admin.site.register(Reflection)
admin.site.register(Observation, ObservationAdmin)
admin.site.register(ObservationType, ObservationTypeAdmin)

