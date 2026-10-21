from django.core.management.base import BaseCommand

from tracker.models import Application
from tracker.services import liveness


class Command(BaseCommand):
    help = "Check whether open applications' postings are still live."

    def handle(self, *args, **opts):
        run = liveness.start_run(background=False)
        self.stdout.write(f"Checked {run.done} of {run.total} postings" + (f" (error: {run.error})" if run.error else ""))
        for app in Application.objects.exclude(live_state="unknown").order_by("company"):
            self.stdout.write(f"  {app.get_live_state_display():<10} {app.company} - {app.role}")
