from django.core.management.base import BaseCommand

from tracker.models import JobSource
from tracker.seed import ensure_default_sources


class Command(BaseCommand):
    help = (
        "Add any default job source that is missing (public company boards and remote-jobs feeds that need no key). "
        "Safe to run any time; it never changes or removes a source that already exists. New installs get these from the migration."
    )

    def handle(self, *args, **opts):
        added = ensure_default_sources(JobSource)
        total = JobSource.objects.filter(owner__isnull=True).count()
        self.stdout.write(f"Added {added} source(s); {total} site-wide source(s) in total.")
