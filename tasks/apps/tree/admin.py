from django.contrib import admin
from .models import Board, Thread, Plan, Reflection, Observation, ObservationType

# Register your models here.

class ObservationTypeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

admin.site.register(Board)
admin.site.register(Thread)
admin.site.register(Plan)
admin.site.register(Reflection)
admin.site.register(Observation)
admin.site.register(ObservationType, ObservationTypeAdmin)

