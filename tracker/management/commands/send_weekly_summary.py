from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig, UserProfile
from tracker.services import weekly, who


class Command(BaseCommand):
    help = (
        "Email the weekly 'what to do this week' summary to people who turned it on (Profile > Emails). One email per person per run, "
        "never twice in 6 days, nothing when there is nothing to say, only to verified addresses. Off until Site configuration > "
        "Dashboard > weekly_emails_enabled is ticked. Meant for a daily or weekly cron."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Only this username.")
        parser.add_argument("--all-users", action="store_true", help="Every active person who opted in (the default when --user is not given).")

    def handle(self, *args, **opts):
        if not SiteConfig.load().weekly_emails_enabled:
            self.stdout.write("Weekly emails are off (Site configuration > Dashboard). Nothing sent.")
            return
        if opts["user"]:
            try:
                owners = [who.resolve_user(opts["user"])]
            except who.WhoError as exc:
                raise CommandError(str(exc)) from exc
        else:
            owners = list(get_user_model().objects.filter(is_active=True))
        counts = {"sent": 0, "recent": 0, "no_address": 0, "nothing": 0, "opted_out": 0}
        for owner in owners:
            if not UserProfile.for_user(owner).email_weekly:
                counts["opted_out"] += 1
                continue
            counts[weekly.send_weekly_summary(owner)] += 1
        self.stdout.write(
            f"Sent {counts['sent']} weekly email(s); skipped {counts['nothing']} with nothing to say, {counts['recent']} emailed in the last 6 days, "
            f"{counts['no_address']} without a verified email, {counts['opted_out']} who have it off."
        )
