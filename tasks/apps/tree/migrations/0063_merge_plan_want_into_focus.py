from django.db import migrations


def merge_want_into_focus(apps, schema_editor):
    Plan = apps.get_model("tree", "Plan")
    for plan in Plan.objects.all():
        want = (plan.want or "").strip()
        focus = (plan.focus or "").strip()

        if want and focus:
            plan.focus = focus + "\n" + want
            plan.save(update_fields=["focus"])
        elif want and not focus:
            plan.focus = want
            plan.save(update_fields=["focus"])


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0062_projected_outcome_moved"),
    ]

    operations = [
        migrations.RunPython(merge_want_into_focus, migrations.RunPython.noop),
    ]
