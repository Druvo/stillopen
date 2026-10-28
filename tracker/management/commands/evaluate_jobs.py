from django.core.management.base import BaseCommand, CommandError

from tracker.models import Application, SiteConfig
from tracker.services import ai, who


class Command(BaseCommand):
    help = "Evaluate match for one user's applications with their AI provider (or keyword match when AI is off)."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username (default: the only superuser).")
        parser.add_argument("--all", action="store_true", help="Also re-evaluate roles that already have a score.")
        parser.add_argument("--limit", type=int, default=20, help="Maximum number of jobs to evaluate in one run.")

    def handle(self, *args, **opts):
        try:
            owner = who.resolve_user(opts["user"])
        except who.WhoError as exc:
            raise CommandError(str(exc)) from exc
        config = SiteConfig.for_user(owner)
        qs = Application.objects.filter(owner=owner, status__is_terminal=False, archived_at__isnull=True)
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
        self.stdout.write(f"{owner}: evaluated {done} job(s) using '{config.ai_provider}'.")
