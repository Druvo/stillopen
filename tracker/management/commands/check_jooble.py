from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig
from tracker.services import scan
from tracker.services.netguard import FetchError


class Command(BaseCommand):
    help = (
        "Try the Jooble key with one real search, so you know it works before relying on it. "
        "The key comes from Site configuration or JOOBLE_API_KEY and is never printed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--place", default="my", help=f"Country code to try ({', '.join(scan.JOOBLE_PLACES)}). Default: my.")
        parser.add_argument("--role", default="software engineer", help="Job title to search for.")

    def handle(self, *args, **opts):
        key = SiteConfig.load().effective_jooble_key
        if not key:
            raise CommandError("No Jooble key yet. Request a free one at https://jooble.org/api/about, then paste it under Site configuration > Job search keys (or set JOOBLE_API_KEY).")
        place = opts["place"].lower()
        if place not in scan.JOOBLE_PLACES:
            raise CommandError(f"Unknown place. Use one of: {', '.join(scan.JOOBLE_PLACES)}.")
        try:
            jobs = scan.fetch_jooble(place, [opts["role"]], key)
        except FetchError as exc:
            raise CommandError(str(exc)) from exc
        if not jobs:
            self.stdout.write(self.style.WARNING(f"The key was accepted but Jooble returned no '{opts['role']}' jobs for {scan.JOOBLE_PLACES[place]}. Try another --role."))
            return
        self.stdout.write(self.style.SUCCESS(f"Jooble works: {len(jobs)} job(s) for '{opts['role']}' in {scan.JOOBLE_PLACES[place]}. For example:"))
        for job in jobs[:5]:
            self.stdout.write(f"  - {job['title']} at {job['company'] or '?'} ({job['location']})")
