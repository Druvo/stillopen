from django.db import migrations

FIELDS = ("sponsorship", "relocation", "employment_type", "seniority")


def backfill(apps, schema_editor):
    """Read what the saved title and excerpt already say; the next refresh fills the rest from the full posting."""
    from tracker.services import geo

    Posting = apps.get_model("tracker", "Posting")
    batch = []
    for p in Posting.objects.only("id", "title", "excerpt").iterator(chunk_size=2000):
        found = geo.detect_terms(p.title, p.excerpt)
        if not found:
            continue
        for name in FIELDS:
            setattr(p, name, found.get(name, ""))
        batch.append(p)
        if len(batch) >= 1000:
            Posting.objects.bulk_update(batch, FIELDS)
            batch = []
    if batch:
        Posting.objects.bulk_update(batch, FIELDS)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0041_posting_terms")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
