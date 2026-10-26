from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tracker.models import SiteConfig, UserProfile
from tracker.services import pipeline, who


class Command(BaseCommand):
    help = (
        "Email anyone with Job alerts on a plain weekly summary (applications sent, interviews, offers, follow-ups). "
        "Meant for a weekly cron. Off until Site configuration > Dashboard > weekly_digest_site_enabled is ticked."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Only this username (they must still have the weekly digest on).")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        if not config.weekly_digest_site_enabled:
            self.stdout.write("The weekly digest is off (Site configuration > Dashboard). Nothing sent.")
            return
        people = get_user_model().objects.filter(is_active=True, profile__weekly_digest_enabled=True)
        if opts["user"]:
            try:
                people = people.filter(pk=who.resolve_user(opts["user"]).pk)
            except who.WhoError as exc:
                raise CommandError(str(exc)) from exc
        today = timezone.localdate()
        monday = today - timezone.timedelta(days=today.weekday())
        sent = skipped_already = 0
        for owner in people:
            if owner.profile.weekly_digest_sent_through == monday:
                skipped_already += 1
                continue
            if pipeline.send_weekly_digest(owner, today):
                sent += 1
            UserProfile.objects.filter(pk=owner.profile.pk).update(weekly_digest_sent_through=monday)
        self.stdout.write(f"Sent {sent} digest email(s); {skipped_already} already sent this week.")
