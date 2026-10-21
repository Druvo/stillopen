from django.conf import settings
from django.db import migrations

from tracker import seed


def apply_seed(apps, schema_editor):
    Bucket = apps.get_model("tracker", "Bucket")
    Status = apps.get_model("tracker", "Status")
    ScoreBand = apps.get_model("tracker", "ScoreBand")
    DocumentKind = apps.get_model("tracker", "DocumentKind")
    Source = apps.get_model("tracker", "Source")
    ExpiredPhrase = apps.get_model("tracker", "ExpiredPhrase")
    SiteConfig = apps.get_model("tracker", "SiteConfig")

    buckets = {}
    for key, label, order, is_closed, description in seed.BUCKETS:
        buckets[key], _ = Bucket.objects.get_or_create(
            key=key, defaults={"label": label, "order": order, "is_closed": is_closed, "description": description}
        )
    for name, bucket, order, color, applied, terminal in seed.STATUSES:
        Status.objects.get_or_create(
            name=name,
            defaults={
                "bucket": buckets[bucket],
                "order": order,
                "color": color,
                "counts_as_applied": applied,
                "is_terminal": terminal,
            },
        )
    for label, minimum, color in seed.SCORE_BANDS:
        ScoreBand.objects.get_or_create(label=label, defaults={"min_percent": minimum, "color": color})
    for name, keywords, tag, doc_type, order in seed.DOCUMENT_KINDS:
        DocumentKind.objects.get_or_create(
            name=name,
            defaults={"keywords": keywords, "paperless_tag": tag, "paperless_document_type": doc_type, "order": order},
        )
    for name, host in seed.SOURCES:
        Source.objects.get_or_create(name=name, defaults={"host_contains": host})
    for phrase, note in seed.EXPIRED_PHRASES:
        ExpiredPhrase.objects.get_or_create(phrase=phrase, defaults={"note": note})

    careerops_path = getattr(settings, "CAREEROPS_PATH_DEFAULT", "")
    SiteConfig.objects.get_or_create(
        pk=1,
        defaults={
            # The career-ops checker renders pages in a browser, so it catches closed postings the plain HTTP check misses.
            "liveness_mode": "node" if careerops_path else "http",
            "careerops_path": careerops_path,
            "node_command": getattr(settings, "NODE_COMMAND_DEFAULT", "node"),
            "paperless_url": getattr(settings, "PAPERLESS_URL_DEFAULT", ""),
        },
    )


class Migration(migrations.Migration):
    dependencies = [("tracker", "0001_initial")]
    operations = [migrations.RunPython(apply_seed, migrations.RunPython.noop)]
