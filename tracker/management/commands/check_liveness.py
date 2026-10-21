from django.core.management.base import BaseCommand, CommandError

from tracker.models import Application
from tracker.services import liveness, who


class Command(BaseCommand):
    help = "Check whether open applications' postings are still live. One user, or --all-users."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username (default: the only superuser).")
        parser.add_argument("--all-users", action="store_true", help="Run for every user, one after another (for a scheduled job).")

    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model

        try:
            owners = list(get_user_model().objects.filter(is_active=True)) if opts["all_users"] else [who.resolve_user(opts["user"])]
        except who.WhoError as exc:
            raise CommandError(str(exc)) from exc
        for owner in owners:
            run = liveness.start_run(owner, background=False)
            self.stdout.write(f"{owner}: checked {run.done} of {run.total} postings" + (f" (error: {run.error})" if run.error else ""))
            if not opts["all_users"]:
                for app in Application.objects.filter(owner=owner).exclude(live_state="unknown").order_by("company"):
                    self.stdout.write(f"  {app.get_live_state_display():<10} {app.company} - {app.role}")
