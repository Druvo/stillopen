from django.core.management.base import BaseCommand

from tracker.services import public


class Command(BaseCommand):
    help = (
        "Refresh the public job board: read every source marked 'show publicly' and mark what is still listed. "
        "Meant for a cron every few hours (the board also refreshes itself when a visitor arrives and it is stale). Needs no AI."
    )

    def handle(self, *args, **opts):
        result = public.refresh_now()
        self.stdout.write(
            f"Read {result['sources']} public source(s); {result['postings']} opening(s) seen; {result['errors']} source(s) did not answer."
        )
