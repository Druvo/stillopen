from django.db import migrations


def soften(apps, schema_editor):
    """The shipped lowest band was called "Weak" in red. Rename it only if nobody has edited it."""
    ScoreBand = apps.get_model("tracker", "ScoreBand")
    ScoreBand.objects.filter(label="Weak", min_percent=0, color="#f16565").update(label="A stretch", color="#e8935a")


class Migration(migrations.Migration):
    dependencies = [("tracker", "0023_saved_status_and_existing_users_welcomed")]
    operations = [migrations.RunPython(soften, migrations.RunPython.noop)]
