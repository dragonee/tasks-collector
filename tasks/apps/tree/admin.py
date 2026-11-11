from datetime import datetime

from django.contrib import admin

from polymorphic.admin import PolymorphicChildModelAdmin, PolymorphicParentModelAdmin

from .models import *
from .services.observations.closing import close_observation
from .services.tasks import documents


class ObservationTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "color")
    prepopulated_fields = {"slug": ("name",)}


class HabitKeywordInline(admin.TabularInline):
    model = HabitKeyword
    extra = 1


class HabitAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "user", "display_keywords", "event_stream_id")
    list_filter = ("user",)
    readonly_fields = ("event_stream_id",)
    inlines = [HabitKeywordInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("keywords")

    def display_keywords(self, obj):
        return ", ".join(obj.get_keywords())

    display_keywords.short_description = "Keywords"


class NamedAfterThreadAdmin(admin.ModelAdmin):
    """Boards, plans and reflections, whose names show their thread."""

    list_select_related = ("thread",)


class PlanLineInline(admin.TabularInline):
    model = PlanLine
    extra = 0
    raw_id_fields = ("task",)


class ReflectionLineInline(admin.TabularInline):
    model = ReflectionLine
    extra = 0
    raw_id_fields = ("task", "completion")


class DocumentAdmin(NamedAfterThreadAdmin):
    """A plan or a reflection, with its lines."""

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        documents.write_copy(form.instance)


class PlanAdmin(DocumentAdmin):
    inlines = [PlanLineInline]


class ReflectionAdmin(DocumentAdmin):
    inlines = [ReflectionLineInline]


class ThreadAdmin(admin.ModelAdmin):
    list_display = ("name", "user")
    list_filter = ("user",)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("name", "user")

        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        # Built-in threads go only together with their owner.
        if obj is not None and obj.is_builtin:
            return False
        return super().has_delete_permission(request, obj)


@admin.action(description="Close selected observations")
def close_observations(modeladmin, request, queryset):
    # Like any other admin write, the close is credited to the observation's
    # owner, not to the admin who ran the action.
    for observation in queryset:
        close_observation(observation.pk)


class ObservationUpdatedInline(admin.StackedInline):
    model = ObservationUpdated

    fields = ("published", "comment")
    readonly_fields = ("published",)


class ObservationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "thread", "type")
    readonly_fields = ("event_stream_id",)

    actions = [close_observations]

    inlines = [ObservationUpdatedInline]


class EventAdmin(PolymorphicParentModelAdmin):
    base_model = Event

    list_display = ("event_name", "published", "thread", "event_stream_id")

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
        PhotoAdded,
        ProjectedOutcomeMade,
        ProjectedOutcomeRedefined,
        ProjectedOutcomeRescheduled,
        ProjectedOutcomeClosed,
        InsightRefined,
        TaskCompleted,
    ]

    ordering = ["-published", "-pk"]

    def event_name(self, obj):
        return str(obj)

    event_name.short_description = "Event"
    event_name.admin_order_field = "pk"


class HabitTrackedAdmin(PolymorphicChildModelAdmin):
    base_model = HabitTracked
    list_select_related = ("habit",)


class ObservationUpdatedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationUpdated

    list_display = ("__str__", "event_stream_id", "published")


class BoardCommittedAdmin(PolymorphicChildModelAdmin):
    base_model = BoardCommitted
    list_display = (
        "__str__",
        "event_stream_id",
    )


class ObservationMadeAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationMade
    list_select_related = ("thread",)


class ObservationRecontextualizedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationRecontextualized


class ObservationReinterpretedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationReinterpreted


class ObservationReflectedUponAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationReflectedUpon


class ObservationClosedAdmin(PolymorphicChildModelAdmin):
    base_model = ObservationClosed


class InsightRefinedAdmin(PolymorphicChildModelAdmin):
    base_model = InsightRefined
    list_select_related = ("thread",)


class TaskCompletedAdmin(PolymorphicChildModelAdmin):
    base_model = TaskCompleted
    list_select_related = ("thread",)
    raw_id_fields = ("task", "journal")


class TaskAdmin(admin.ModelAdmin):
    list_display = ("text", "user", "done_count", "completed_at", "created")
    list_filter = ("user",)
    list_select_related = ("user",)
    search_fields = ("text", "anchor")
    raw_id_fields = ("user", "board")
    readonly_fields = ("anchor",)


class JournalAddedAdmin(PolymorphicChildModelAdmin):
    base_model = JournalAdded

    list_display = ("__str__", "thread", "published")


class PhotoAddedAdmin(PolymorphicChildModelAdmin):
    base_model = PhotoAdded

    list_display = ("__str__", "thread", "published", "thumbnail_key")


class ProjectedOutcomeMadeAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeMade
    list_select_related = ("projected_outcome",)

    list_display = ("__str__", "projected_outcome", "name", "resolved_by", "published")
    list_filter = ("resolved_by", "published")
    search_fields = ("name", "description")
    readonly_fields = ("event_stream_id", "published")


class ProjectedOutcomeRedefinedAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeRedefined
    list_select_related = ("projected_outcome",)

    list_display = ("__str__", "projected_outcome", "published")
    list_filter = ("published",)
    readonly_fields = ("event_stream_id", "published")


class ProjectedOutcomeRescheduledAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeRescheduled
    list_select_related = ("projected_outcome",)

    list_display = (
        "__str__",
        "projected_outcome",
        "old_resolved_by",
        "new_resolved_by",
        "published",
    )
    list_filter = ("old_resolved_by", "new_resolved_by", "published")
    readonly_fields = ("event_stream_id", "published")


class ProjectedOutcomeClosedAdmin(PolymorphicChildModelAdmin):
    base_model = ProjectedOutcomeClosed
    list_select_related = ("projected_outcome",)

    list_display = ("__str__", "projected_outcome", "name", "resolved_by", "published")
    list_filter = ("resolved_by", "published")
    search_fields = ("name", "description")
    readonly_fields = ("event_stream_id", "published")


class ProjectedOutcomeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "breakthrough",
        "resolved_by",
        "confidence_level",
        "published",
    )
    list_filter = ("resolved_by", "published", "breakthrough")
    search_fields = ("name", "description")
    readonly_fields = ("event_stream_id", "published")


class BreakthroughAdmin(admin.ModelAdmin):
    list_display = ("slug", "theme", "published")
    list_filter = ("published",)
    search_fields = ("slug", "theme", "areas_of_concern")
    readonly_fields = ("published",)


class JournalTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "user")
    list_filter = ("user",)

    prepopulated_fields = {"slug": ("name",)}


class EventStreamAccessInline(admin.TabularInline):
    model = EventStreamAccess
    extra = 0
    raw_id_fields = ("user",)


class EventStreamAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "created_by", "created")
    list_filter = ("type", "created_by")
    search_fields = ("id",)
    raw_id_fields = ("created_by",)
    inlines = [EventStreamAccessInline]


admin.site.register(Board, NamedAfterThreadAdmin)
admin.site.register(Thread, ThreadAdmin)
admin.site.register(Plan, PlanAdmin)
admin.site.register(Reflection, ReflectionAdmin)
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
admin.site.register(PhotoAdded, PhotoAddedAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(JournalTag, JournalTagAdmin)
admin.site.register(Breakthrough, BreakthroughAdmin)
admin.site.register(EventStream, EventStreamAdmin)
admin.site.register(ProjectedOutcome, ProjectedOutcomeAdmin)
admin.site.register(ProjectedOutcomeMade, ProjectedOutcomeMadeAdmin)
admin.site.register(ProjectedOutcomeRedefined, ProjectedOutcomeRedefinedAdmin)
admin.site.register(ProjectedOutcomeRescheduled, ProjectedOutcomeRescheduledAdmin)
admin.site.register(ProjectedOutcomeClosed, ProjectedOutcomeClosedAdmin)
admin.site.register(InsightRefined, InsightRefinedAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(TaskCompleted, TaskCompletedAdmin)
