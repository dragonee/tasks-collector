from django.apps import AppConfig


class TreeConfig(AppConfig):
    name = "tasks.apps.tree"

    def ready(self):
        from . import signals  # noqa: F401
