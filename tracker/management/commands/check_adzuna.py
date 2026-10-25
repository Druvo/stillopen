from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig
from tracker.services import adzuna
from tracker.services.netguard import FetchError


class Command(BaseCommand):
    help = (
        "Try the Adzuna app id and key with one real search, so you know they work before relying on them. "
        "They come from Site configuration or ADZUNA_APP_ID / ADZUNA_APP_KEY; the key is never printed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--country", default="gb", help=f"Country code to try ({', '.join(adzuna.COUNTRIES)}). Default: gb.")
        parser.add_argument("--role", default="software engineer", help="Job title to search for.")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        app_id, app_key = config.effective_adzuna_id, config.effective_adzuna_key
        if not (app_id and app_key):
            raise CommandError(
                "No Adzuna keys yet. Register free at https://developer.adzuna.com, then paste the app id and key under "
                "Site configuration > Job search keys (or set ADZUNA_APP_ID and ADZUNA_APP_KEY)."
            )
        country = opts["country"].lower()
        if country not in adzuna.COUNTRIES:
            raise CommandError(f"Unknown country. Use one of: {', '.join(adzuna.COUNTRIES)}.")
        name = adzuna.COUNTRIES[country][0]
        try:
            jobs = adzuna.fetch_adzuna(country, [opts["role"]], (app_id, app_key))
        except FetchError as exc:
            raise CommandError(str(exc)) from exc
        if not jobs:
            self.stdout.write(self.style.WARNING(f"The keys were accepted but Adzuna returned no '{opts['role']}' jobs for {name}. Try another --role."))
            return
        self.stdout.write(self.style.SUCCESS(f"Adzuna works: {len(jobs)} job(s) for '{opts['role']}' in {name}. For example:"))
        for job in jobs[:5]:
            self.stdout.write(f"  - {job['title']} at {job['company'] or '?'} ({job['location']})")
        self.stdout.write("Jobs by Adzuna: show this credit wherever the results appear (the app already does).")
