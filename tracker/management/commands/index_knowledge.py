from django.core.management.base import BaseCommand, CommandError

from tracker.models import KnowledgeChunk, KnowledgeSource, SiteConfig
from tracker.services import knowledge, who


class Command(BaseCommand):
    help = "Build one user's knowledge base: import career-ops files (admins), rebuild passages, optionally compute embeddings."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="Username (default: the only superuser).")
        parser.add_argument("--import-careerops", action="store_true", help="Import cv.md, article-digest.md and modes/_profile.md (admins).")
        parser.add_argument("--embed", action="store_true", help="Compute embeddings for passages that have none.")

    def handle(self, *args, **opts):
        try:
            owner = who.resolve_user(opts["user"])
        except who.WhoError as exc:
            raise CommandError(str(exc)) from exc
        config = SiteConfig.for_user(owner)
        if opts["import_careerops"]:
            if not owner.is_staff:
                raise CommandError("Only site admins can import from a career-ops folder.")
            self.stdout.write("Imported: " + (", ".join(knowledge.import_careerops(config, owner)) or "nothing found"))
        knowledge.sync_cv(config, owner)
        sources = KnowledgeSource.objects.filter(owner=owner)
        total = sum(knowledge.reindex_source(s, config) for s in sources)
        self.stdout.write(f"{owner}: {sources.count()} source(s), {total} passage(s).")
        if opts["embed"]:
            try:
                done = knowledge.embed_pending(config, owner)
            except knowledge.KnowledgeError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"Embedded {done} passage(s); {KnowledgeChunk.objects.filter(source__owner=owner).exclude(embedding=None).count()} in total.")
