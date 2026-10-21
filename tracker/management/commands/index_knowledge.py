from django.core.management.base import BaseCommand, CommandError

from tracker.models import KnowledgeChunk, KnowledgeSource, SiteConfig
from tracker.services import knowledge


class Command(BaseCommand):
    help = "Build the candidate knowledge base: import career-ops files, rebuild passages, optionally compute embeddings."

    def add_arguments(self, parser):
        parser.add_argument("--import-careerops", action="store_true", help="Import cv.md, article-digest.md and modes/_profile.md.")
        parser.add_argument("--embed", action="store_true", help="Compute embeddings for passages that have none.")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        if opts["import_careerops"]:
            self.stdout.write("Imported: " + (", ".join(knowledge.import_careerops(config)) or "nothing found"))
        knowledge.sync_cv(config)
        total = sum(knowledge.reindex_source(s, config) for s in KnowledgeSource.objects.all())
        self.stdout.write(f"{KnowledgeSource.objects.count()} source(s), {total} passage(s).")
        if opts["embed"]:
            try:
                done = knowledge.embed_pending(config)
            except knowledge.KnowledgeError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"Embedded {done} passage(s); {KnowledgeChunk.objects.exclude(embedding=None).count()} in total.")
