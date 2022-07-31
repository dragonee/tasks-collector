from django.db import models

from django.utils.translation import ugettext_lazy as _

from django.core.validators import MaxValueValidator, MinValueValidator


class Reward(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)

    description = models.TextField(
        help_text=_("Describe the reward"),
        blank=True,
        null=True,
    )

    choose_one = models.BooleanField(
        _("OR"),
        help_text=_("Unselect to get all items from reward table"),
        default=True
    )

    def __str__(self):
        return self.name

    def has_table(self) -> bool:
        return self.table.count() > 0
    
    has_table.boolean = True


class RewardTableItem(models.Model):
    count = models.PositiveSmallIntegerField(default=1)
    calculate_each = models.BooleanField(_("Each"), default=True)
    fail_percent = models.PositiveSmallIntegerField(
        _("%0"),
        default=0,
        validators=[
            MaxValueValidator(100),
            MinValueValidator(0)
        ]
    )

    table = models.ForeignKey(Reward, related_name="table", on_delete=models.CASCADE)
    item = models.ForeignKey(Reward, related_name="+", on_delete=models.CASCADE)

    def __str__(self):
        return self.item.name