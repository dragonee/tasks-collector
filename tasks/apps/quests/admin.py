from django.contrib import admin

from .models import Quest, QuestJournal


class QuestJournalInline(admin.TabularInline):
    model = QuestJournal


class QuestAdmin(admin.ModelAdmin):
    model = Quest

    inlines = [QuestJournalInline]


admin.site.register(Quest, QuestAdmin)
