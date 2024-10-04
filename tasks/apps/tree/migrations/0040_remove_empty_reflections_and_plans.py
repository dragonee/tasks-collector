# Generated by Django 4.2.16 on 2024-10-04 18:04

from django.db import migrations


def is_empty(object, fields):
    return all(not getattr(object, field) for field in fields)


def find_empty_objects(model, fields):
    objects = model.objects.all()

    return filter(lambda object: is_empty(object, fields), objects)


def remove_empty_objects(model, fields):
    empty_objects = find_empty_objects(model, fields)

    for empty_object in empty_objects:
        empty_object.delete()


def run_function(apps, schema_editor):
    remove_empty_objects(apps.get_model("tree", "Reflection"), ["good", "better", "best"])
    remove_empty_objects(apps.get_model("tree", "Plan"), ["focus", "want"])


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0039_habit_description"),
    ]

    operations = [
        migrations.RunPython(run_function),
    ]
