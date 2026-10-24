from django.db import migrations


def apply(apps, schema_editor):
    # People who already use the app have no need for the first-run welcome.
    apps.get_model("tracker", "UserProfile").objects.update(onboarding_done=True)

    # A job you have only just added is "Saved", not "Evaluated". It becomes Evaluated once its fit is checked.
    Status = apps.get_model("tracker", "Status")
    Bucket = apps.get_model("tracker", "Bucket")
    if not Status.objects.filter(name__iexact="Saved").exists():
        bucket = (Status.objects.filter(name="Evaluated").first() or Status.objects.order_by("order").first())
        target = bucket.bucket if bucket else Bucket.objects.filter(is_closed=False).order_by("order").first()
        if target is not None:
            Status.objects.create(name="Saved", bucket=target, order=0, color="#8b93a7", counts_as_applied=False, is_terminal=False)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0022_onboarding_done")]
    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
