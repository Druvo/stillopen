from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig, UserProfile
from tracker.services import pipeline, who


class Command(BaseCommand):
    help = (
        "Email anyone with an interview in the next 24 hours, once per interview. One email per person per run. "
        "Meant for an hourly cron. Uses the same switch as follow-up emails (Site configuration > Dashboard)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Only this username (default: every active user).")

    def handle(self, *args, **opts):
        if not SiteConfig.load().followup_emails_enabled:
            self.stdout.write("Reminder emails are off (Site configuration > Dashboard). Nothing sent.")
            return
        if opts["user"]:
            try:
                owners = [who.resolve_user(opts["user"])]
            except who.WhoError as exc:
                raise CommandError(str(exc)) from exc
        else:
            owners = list(get_user_model().objects.filter(is_active=True))
        owners = [o for o in owners if UserProfile.for_user(o).email_interviews]  # the person's own choice, once the admin switch is on
        sent = skipped = 0
        for owner in owners:
            items = pipeline.due_interview_reminders(owner)
            if pipeline.send_interview_reminders(owner, items):
                sent += 1
            elif items:
                skipped += 1
        self.stdout.write(f"Sent {sent} reminder email(s); {skipped} person(s) had interviews soon but no verified email.")
