from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tracker.models import JobSource, SiteConfig
from tracker.services import scan, who


class Command(BaseCommand):
    help = (
        "Run the job search for everyone who turned on Job alerts and email each person one list of what was added. "
        "Meant for a daily cron. Off until Site configuration > Dashboard > scan_emails_enabled is ticked."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Only this username (they must still have Job alerts on).")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        if not config.scan_emails_enabled:
            self.stdout.write("Scheduled job alerts are off (Site configuration > Dashboard). Nothing run.")
            return
        people = get_user_model().objects.filter(is_active=True, profile__scan_digest_enabled=True)
        if opts["user"]:
            try:
                people = people.filter(pk=who.resolve_user(opts["user"]).pk)
            except who.WhoError as exc:
                raise CommandError(str(exc)) from exc
        searched = emailed = 0
        for owner in people:
            if not JobSource.for_user(owner, enabled=True).exists():
                continue
            run = scan.start_run(owner, background=False)
            searched += 1
            if scan.send_scan_digest(owner, run):
                emailed += 1
        self.stdout.write(f"Searched for {searched} person(s); emailed {emailed}.")
