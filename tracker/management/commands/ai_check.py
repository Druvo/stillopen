from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig
from tracker.services import ai, who


class Command(BaseCommand):
    help = "Send one tiny request to a user's configured AI provider and report whether it answered usably."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username (default: the only superuser).")

    def handle(self, *args, **opts):
        try:
            owner = who.resolve_user(opts["user"])
        except who.WhoError as exc:
            raise CommandError(str(exc)) from exc
        config = SiteConfig.for_user(owner)
        if config.ai_provider == "none":
            raise CommandError(f"{owner}: AI provider is 'Off'. Choose one in AI settings first.")
        backend = ai.BACKENDS[config.ai_provider]
        system = 'Reply with exactly this JSON and nothing else: {"ok": true}'
        try:
            text = backend(system, "ping", config)
        except ai.AIError as exc:
            raise CommandError(f"{config.get_ai_provider_display()}: {exc}") from exc
        self.stdout.write(f"Provider '{config.ai_provider}' answered ({len(text)} characters): {text[:120]!r}")
