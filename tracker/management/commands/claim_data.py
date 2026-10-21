from django.core.management.base import BaseCommand, CommandError

from tracker.services import claim, who


class Command(BaseCommand):
    help = "Give jobs, documents and settings created before accounts existed (single-user installs) to one user."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **opts):
        try:
            user = who.resolve_user(opts["username"])
        except who.WhoError as exc:
            raise CommandError(str(exc)) from exc
        counts = claim.claim_orphans(user)
        self.stdout.write(
            f"{user}: {counts['applications']} application(s), {counts['knowledge']} document(s) assigned"
            + ("; profile seeded from the old site settings" if counts["profile_seeded"] else "")
        )
