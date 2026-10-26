from django.db import migrations, models

# "Discarded" read like something that happened to the job and "SKIP" (all capitals) said the same thing twice. Plain names instead.
# The old names still work wherever a name arrives from outside (the career-ops import, the assistant): see board.STATUS_ALIASES.
RENAMES = [("Discarded", "Not for me"), ("SKIP", "Skipped")]


def rename_statuses(apps, schema_editor):
    Status = apps.get_model("tracker", "Status")
    for old, new in RENAMES:
        status = Status.objects.filter(name=old).first()
        if status is None or Status.objects.filter(name=new).exists():
            continue  # already renamed, or the admin made one of that name: leave both alone
        status.name = new
        status.save(update_fields=["name"])


def restore_statuses(apps, schema_editor):
    Status = apps.get_model("tracker", "Status")
    for old, new in RENAMES:
        status = Status.objects.filter(name=new).first()
        if status is not None and not Status.objects.filter(name=old).exists():
            status.name = old
            status.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [("tracker", "0056_hardening_timezone_signup_protection")]

    operations = [
        migrations.AddField(
            model_name="event",
            name="undo",
            field=models.JSONField(
                blank=True, default=None, editable=False, null=True,
                help_text="For a status change: what the job looked like before it (status, applied date, follow-up date), so the person can undo it for a few minutes. See services/board.py.",
            ),
        ),
        migrations.RunPython(rename_statuses, restore_statuses),
    ]
