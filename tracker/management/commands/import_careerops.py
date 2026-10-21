from django.core.management.base import BaseCommand, CommandError

from tracker.models import Document, SiteConfig
from tracker.services import careerops
from tracker.services.paperless import PaperlessClient, PaperlessError, push_document


class Command(BaseCommand):
    help = "Import the career-ops tracker, reports and PDFs. Existing statuses are kept unless --sync-status is given."

    def add_arguments(self, parser):
        parser.add_argument("--sync-status", action="store_true", help="Overwrite statuses with the tracker's values.")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        try:
            counts = careerops.import_all(config, sync_status=opts["sync_status"])
        except careerops.ImportErrorMessage as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"{counts['created']} created, {counts['updated']} refreshed, {counts['documents']} documents linked")

        if config.paperless_enabled and config.paperless_auto_upload:
            try:
                client = PaperlessClient.from_config(config)
            except PaperlessError as exc:
                raise CommandError(str(exc)) from exc
            pushed = sum(
                1
                for d in Document.objects.filter(paperless_id__isnull=True).select_related("application", "kind")
                if push_document(d, client, config)
            )
            self.stdout.write(f"{pushed} documents sent to Paperless")
