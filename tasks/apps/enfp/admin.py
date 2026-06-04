from django.contrib import admin

from .models import Challenge, ChallengeStage, ChallengeStageCompleted, Element


class ChallengeStageInline(admin.TabularInline):
    model = ChallengeStage
    extra = 1


class ChallengeAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("__str__", "slug", "active", "started_at", "completed_at")
    inlines = [ChallengeStageInline]


class ElementAdmin(admin.ModelAdmin):
    list_display = ("__str__", "function", "published")
    list_filter = ("function",)


admin.site.register(Element, ElementAdmin)
admin.site.register(Challenge, ChallengeAdmin)
admin.site.register(ChallengeStageCompleted)
