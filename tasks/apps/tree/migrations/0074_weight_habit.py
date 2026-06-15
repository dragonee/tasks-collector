from django.db import migrations


WEIGHT_SLUG = "weight"
WEIGHT_NAME = "Weight"
WEIGHT_DESCRIPTION = (
    "Body weight recorded from the Health screen. "
    "Tracked via the #weight hashtag; the note carries weight=<float>kg."
)
WEIGHT_KEYWORDS = ("weight",)


def create_weight_habit(apps, schema_editor):
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    db_alias = schema_editor.connection.alias

    habit, _ = Habit.objects.using(db_alias).get_or_create(
        slug=WEIGHT_SLUG,
        defaults={"name": WEIGHT_NAME, "description": WEIGHT_DESCRIPTION},
    )

    for keyword in WEIGHT_KEYWORDS:
        HabitKeyword.objects.using(db_alias).get_or_create(
            keyword=keyword, defaults={"habit": habit}
        )


def remove_weight_habit(apps, schema_editor):
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    db_alias = schema_editor.connection.alias

    HabitKeyword.objects.using(db_alias).filter(keyword__in=WEIGHT_KEYWORDS).delete()
    Habit.objects.using(db_alias).filter(slug=WEIGHT_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0073_sharedstory"),
    ]

    operations = [
        migrations.RunPython(create_weight_habit, remove_weight_habit),
    ]
