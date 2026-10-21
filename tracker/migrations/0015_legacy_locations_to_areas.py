from django.db import migrations


def locations_to_areas(apps, schema_editor):
    """Turn the old free-text 'locations' lines and single 'remote preference' into search area rows."""
    UserProfile = apps.get_model("tracker", "UserProfile")
    SearchArea = apps.get_model("tracker", "SearchArea")
    for profile in UserProfile.objects.all():
        if SearchArea.objects.filter(owner_id=profile.user_id).exists():
            continue
        lines = [l.strip() for l in (profile.locations or "").splitlines() if l.strip()]
        pref = profile.remote_preference or "any"
        if not lines and pref == "any":
            continue
        remote, hybrid, onsite = {
            "remote": (True, False, False),
            "hybrid": (False, True, False),
            "onsite": (False, False, True),
            "relocate": (True, True, True),
            "any": (True, True, True),
        }.get(pref, (True, True, True))
        for position, line in enumerate(lines or ["Anywhere"]):
            anywhere = line.lower() in ("remote", "anywhere", "worldwide", "global")
            SearchArea.objects.create(
                owner_id=profile.user_id, order=position, place="Anywhere" if anywhere else line,
                allow_remote=True if anywhere else remote, allow_hybrid=False if anywhere else hybrid,
                allow_onsite=False if anywhere else onsite,
            )


class Migration(migrations.Migration):
    dependencies = [("tracker", "0014_search_areas_and_job_details")]
    operations = [migrations.RunPython(locations_to_areas, migrations.RunPython.noop)]
