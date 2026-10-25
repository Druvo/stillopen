from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig, UserProfile
from tracker.services import apply as apply_service
from tracker.services import who


class Command(BaseCommand):
    help = "Email anyone with a follow-up newly due today. One digest per person, never one email per job. Meant for a daily cron."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Only this username (default: every active user).")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        if not config.followup_emails_enabled:
            self.stdout.write("Follow-up emails are off (Site configuration > Dashboard). Nothing sent.")
            return
        if opts["user"]:
            try:
                owners = [who.resolve_user(opts["user"])]
            except who.WhoError as exc:
                raise CommandError(str(exc)) from exc
        else:
            owners = list(get_user_model().objects.filter(is_active=True))
        owners = [o for o in owners if UserProfile.for_user(o).email_followups]  # the person's own choice, once the admin switch is on
        sent, skipped = 0, 0
        for owner in owners:
            apps = apply_service.due_followups_to_email(owner)
            if apply_service.send_followup_digest(owner, apps):
                sent += 1
            elif apps:
                skipped += 1  # had something due, but no verified email to send it to
        self.stdout.write(f"Sent {sent} digest email(s); {skipped} person(s) had follow-ups due but no verified email.")
