from django.db import migrations


POI_SLUG = "poi"
POI_NAME = "POI"
POI_DESCRIPTION = (
    "Point of interest recorded during a Trip. "
    "Tracked via #poi/#coords/#coordinates/#latlng hashtags "
    "in journal entries; the note typically carries "
    "lat=<float> lng=<float> (and optionally acc=<float>)."
)
POI_KEYWORDS = ("poi", "coords", "coordinates", "latlng")


def create_poi_habit(apps, schema_editor):
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    db_alias = schema_editor.connection.alias

    habit, _ = Habit.objects.using(db_alias).get_or_create(
        slug=POI_SLUG,
        defaults={"name": POI_NAME, "description": POI_DESCRIPTION},
    )

    for keyword in POI_KEYWORDS:
        HabitKeyword.objects.using(db_alias).get_or_create(
            keyword=keyword, defaults={"habit": habit}
        )


def remove_poi_habit(apps, schema_editor):
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    db_alias = schema_editor.connection.alias

    HabitKeyword.objects.using(db_alias).filter(keyword__in=POI_KEYWORDS).delete()
    Habit.objects.using(db_alias).filter(slug=POI_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0067_story_models"),
    ]

    operations = [
        migrations.RunPython(create_poi_habit, remove_poi_habit),
    ]
