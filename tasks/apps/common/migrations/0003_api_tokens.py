"""Tokens of the app's own, one per device or script, in place of the one
token per user of ``rest_framework.authtoken``.

The tokens that app issued keep working: each becomes an ``ApiToken`` with
the digest of its key. Its table, which holds the keys themselves, is then
dropped, and with it the record of its migrations (the app is no longer
installed). Reversing this migration drops the new tables and brings nothing
back: every client has to be given a token again.
"""

import hashlib

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DRF_TABLE = "authtoken_token"
CARRIED_OVER = "Token issued before devices logged in"


def carry_over_drf_tokens(apps, schema_editor):
    connection = schema_editor.connection
    if DRF_TABLE not in connection.introspection.table_names():
        return

    ApiToken = apps.get_model("common", "ApiToken")
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT key, user_id, created FROM {DRF_TABLE}")
        rows = cursor.fetchall()
    for key, user_id, created in rows:
        token = ApiToken.objects.create(
            user_id=user_id,
            name=CARRIED_OVER,
            digest=hashlib.sha256(key.encode()).hexdigest(),
        )
        # ``created`` is set on insert whatever is passed.
        ApiToken.objects.filter(pk=token.pk).update(created=created)

    schema_editor.execute(f"DROP TABLE {DRF_TABLE}")
    schema_editor.execute("DELETE FROM django_migrations WHERE app = 'authtoken'")


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0002_alter_user_first_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApiToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('digest', models.CharField(editable=False, max_length=64, unique=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('last_used', models.DateTimeField(blank=True, editable=False, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='api_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created',),
            },
        ),
        migrations.CreateModel(
            name='AuthorizationCode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('digest', models.CharField(max_length=64, unique=True)),
                ('client_id', models.CharField(max_length=100)),
                ('redirect_uri', models.CharField(max_length=500)),
                ('code_challenge', models.CharField(max_length=128)),
                ('device_name', models.CharField(blank=True, max_length=100)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(carry_over_drf_tokens, migrations.RunPython.noop),
    ]
