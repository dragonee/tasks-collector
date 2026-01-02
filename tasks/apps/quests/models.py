from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Quest(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, primary_key=True)

    stage = models.PositiveSmallIntegerField(default=0)

    date_closed = models.DateField(help_text=_("Closed"), null=True, blank=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("show_quest", kwargs={"slug": self.slug})


class QuestJournal(models.Model):
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE)

    stage = models.PositiveSmallIntegerField(blank=True, null=True)

    pub_date = models.DateTimeField(auto_now_add=True)

    text = models.TextField()
