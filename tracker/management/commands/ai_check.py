from django.core.management.base import BaseCommand, CommandError

from tracker.models import SiteConfig
from tracker.services import ai


class Command(BaseCommand):
    help = "Send one tiny request to the configured AI provider and report whether it answered usably."

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        if config.ai_provider == "none":
            raise CommandError("AI provider is 'Off'. Choose one in Site configuration first.")
        backend = ai.BACKENDS[config.ai_provider]
        system = 'Reply with exactly this JSON and nothing else: {"ok": true}'
        try:
            text = backend(system, "ping", config)
        except ai.AIError as exc:
            raise CommandError(f"{config.get_ai_provider_display()}: {exc}") from exc
        self.stdout.write(f"Provider '{config.ai_provider}' answered ({len(text)} characters): {text[:120]!r}")
