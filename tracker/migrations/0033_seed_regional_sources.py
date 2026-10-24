from django.conf import settings
from django.db import migrations

from tracker.seed_sources import JOOBLE, REGIONAL


def seed(apps, schema_editor):
    """Existing installs get the Malaysia/Gulf/Bangladesh sources once. Only entries that are missing are added, and only
    when the install already uses the default sources (an admin who runs their own list is left alone). Not in tests."""
    if not settings.STILLOPEN_SEED_SOURCES:
        return
    JobSource = apps.get_model("tracker", "JobSource")
    if not JobSource.objects.filter(owner__isnull=True).exists():
        return  # a fresh install: migration 0031 has already added everything
    for name, connector, token in REGIONAL + JOOBLE:
        JobSource.objects.get_or_create(owner=None, connector=connector, board_token=token, defaults={"name": name, "enabled": True})


class Migration(migrations.Migration):
    dependencies = [("tracker", "0032_jooble")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
