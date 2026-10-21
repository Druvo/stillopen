from django.core.management.base import BaseCommand

from tracker.models import Application, SiteConfig
from tracker.services import ai


class Command(BaseCommand):
    help = "Evaluate match for applications with the configured AI provider (or keyword match when AI is off)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Also re-evaluate roles that already have a score.")
        parser.add_argument("--limit", type=int, default=20, help="Maximum number of jobs to evaluate in one run.")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        qs = Application.objects.filter(status__is_terminal=False)
        if not opts["all"]:
            qs = qs.filter(score__isnull=True)  # never replace scores that career-ops or you already set
        done = 0
        for app in qs[: opts["limit"]]:
            try:
                result = ai.evaluate_application(app, config)
            except ai.AIError as exc:
                self.stderr.write(f"{app.company}: {exc}")
                continue
            done += 1
            self.stdout.write(f"{app.company} - {app.role}: {result['match_percent']}% ({app.ai_method})")
        self.stdout.write(f"Evaluated {done} job(s) using '{config.ai_provider}'.")
