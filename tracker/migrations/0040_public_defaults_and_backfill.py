from django.db import migrations

from tracker import copy
from tracker.seed_sources import PUBLIC_OK_CONNECTORS
from tracker.services import geo

import re

_REMOTE = re.compile(r"\bremote\b|\banywhere\b|\bworldwide\b|work from home|\bdistributed\b", re.I)


def forwards(apps, schema_editor):
    JobSource = apps.get_model("tracker", "JobSource")
    Posting = apps.get_model("tracker", "Posting")
    SiteConfig = apps.get_model("tracker", "SiteConfig")

    # Site-wide sources whose own terms allow public display start visible; everything else stays hidden until an admin says so.
    JobSource.objects.filter(owner__isnull=True, connector__in=PUBLIC_OK_CONNECTORS).update(show_publicly=True)

    # Existing postings get the country and remote flag the public board filters on (the excerpt fills in from the next search).
    batch = []
    for posting in Posting.objects.only("id", "location", "title", "country", "remote").iterator(chunk_size=2000):
        codes = geo.location_codes(posting.location)
        country = next(iter(codes)) if len(codes) == 1 else ""
        remote = bool(_REMOTE.search(f"{posting.location} {posting.title}"))
        if country != posting.country or remote != posting.remote:
            posting.country, posting.remote = country, remote
            batch.append(posting)
        if len(batch) >= 1000:
            Posting.objects.bulk_update(batch, ["country", "remote"])
            batch = []
    if batch:
        Posting.objects.bulk_update(batch, ["country", "remote"])

    # An unedited landing page gets the new all-in-one wording; the owner's own words are never touched.
    for config in SiteConfig.objects.all():
        changed = []
        if config.landing_headline.strip() == copy.OLD_HEADLINE:
            config.landing_headline = copy.HEADLINE
            changed.append("landing_headline")
        if config.landing_subheadline.strip() == copy.OLD_SUBHEADLINE:
            config.landing_subheadline = copy.SUBHEADLINE
            changed.append("landing_subheadline")
        if changed:
            config.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0039_landing_copy")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
