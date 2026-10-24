from django.conf import settings
from django.db import migrations

from tracker.seed import ensure_default_sources


def seed(apps, schema_editor):
    """A fresh install starts with working job sources so a candidate sees jobs on day one. Only when there are no
    site-wide sources yet (an admin who set their own up, or removed them all on purpose, is left alone), and not in tests."""
    if not settings.STILLOPEN_SEED_SOURCES:
        return
    JobSource = apps.get_model("tracker", "JobSource")
    if JobSource.objects.filter(owner__isnull=True).exists():
        return
    ensure_default_sources(JobSource)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0030_scan_engine")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
