# Generated by Django 3.2.16 on 2024-08-15 07:47

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0033_auto_20240728_1824'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuickNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('published', models.DateTimeField(default=django.utils.timezone.now)),
                ('note', models.TextField()),
            ],
        ),
    ]