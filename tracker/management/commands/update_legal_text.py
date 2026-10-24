from django.core.management.base import BaseCommand

from tracker import legal
from tracker.models import SiteConfig


class Command(BaseCommand):
    help = (
        "Replace the privacy and terms text with the current template, but only where the site still has an unedited older "
        "default (your own words are never overwritten). --force replaces them regardless."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Replace even text you edited.")

    def handle(self, *args, **opts):
        config = SiteConfig.load()
        changed = []
        for field, old, new in (("privacy_text", legal.OLD_PRIVACY, legal.PRIVACY), ("terms_text", legal.OLD_TERMS, legal.TERMS)):
            current = (getattr(config, field) or "").strip()
            if opts["force"] or not current or current == old.strip():
                setattr(config, field, new)
                changed.append(field)
            else:
                self.stdout.write(f"Kept {field}: it has your own wording (use --force to replace).")
        if changed:
            config.save(update_fields=changed)
            self.stdout.write(self.style.SUCCESS(f"Updated {', '.join(changed)}. Fill in the [bracketed parts] under Site configuration > Legal."))
        else:
            self.stdout.write("Nothing to update.")
