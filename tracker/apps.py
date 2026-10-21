from django.apps import AppConfig


class TrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tracker"
    verbose_name = "StillOpen"

    def ready(self):
        from . import signals  # noqa: F401  (registers the user-created handler)
