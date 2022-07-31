# Generated by Django 3.2.12 on 2022-07-31 10:19

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Quest',
            fields=[
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(max_length=255, primary_key=True, serialize=False)),
                ('stage', models.PositiveSmallIntegerField(default=0)),
                ('date_closed', models.DateField(blank=True, help_text='Closed', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='QuestJournal',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('text', models.TextField()),
                ('quest', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='quests.quest')),
            ],
        ),
    ]