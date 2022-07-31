from django.db import models

from django.utils.translation import ugettext_lazy as _

from django.core.validators import MaxValueValidator, MinValueValidator

from django.urls import reverse

from dataclasses import dataclass
import dataclasses

from typing import List
from functools import reduce

import random
import json


from dataclasses_json import dataclass_json

@dataclass_json
@dataclass
class ClaimedReward:
    name: str
    description: str
    emoji: str
    count: int

    def __eq__(self, __o: object) -> bool:
        return self.name == __o.name and self.description == __o.description
    
    def __hash__(self) -> int:
        return hash((self.name, self.description))


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)

class CRJsonDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        super().__init__(object_hook=self.object_hook, *args, **kwargs)
   
    def object_hook(self, dct):
        if 'name' in dct and 'count' in dct:
            return ClaimedReward(**dct)

        return dct


class Reward(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)

    emoji = models.CharField(max_length=4, null=True, blank=True)

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


class Claim(models.Model):
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE)
    rewarded_for = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.reward.name
    
    def get_absolute_url(self):
        return reverse("claim", kwargs={"id": self.pk})
    

class Claimed(models.Model):
    claimed = models.JSONField(
        null=True, 
        blank=True,
        encoder=DataclassJSONEncoder,
        decoder=CRJsonDecoder,
    )
    claimed_date = models.DateField(help_text=_("Claimed"), null=True, blank=True)

    def __str__(self):
        return str(self.claimed_date)


def claim_reward(reward: Reward, count: int = 1) -> List[ClaimedReward]:
    random.seed()

    rewards = [
        ClaimedReward(
            name=reward.name,
            description=reward.description,
            count=count,
            emoji=reward.emoji,
        )
    ] if reward.description else []

    all_table_items = reward.table.all()

    if len(all_table_items) == 0:
        return rewards

    table_items = [
        random.choice(all_table_items)
    ] if reward.choose_one else all_table_items

    item_rewards = []

    for table_item in table_items:
        if table_item.fail_percent > 0:
            if random.randint(1, 100) <= table_item.fail_percent:
                continue

        new_count = count * table_item.count

        if table_item.calculate_each:
            for _ in range(new_count):
                item_rewards += claim_reward(table_item.item, 1)
        else:
            item_rewards += claim_reward(table_item.item, new_count)
        
    all_rewards = rewards + item_rewards

    def deduplicate(a, r):
        for candidate in a:
            if candidate == r:
                candidate.count += r.count
                return a
        
        return a + [r]
            
    return reduce(deduplicate, all_rewards, [])