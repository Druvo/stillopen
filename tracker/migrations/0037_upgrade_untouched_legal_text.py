from django.db import migrations

from tracker import legal


def upgrade(apps, schema_editor):
    """A site that still has the old placeholder text (never edited) gets the new template; the owner's own words are never touched."""
    SiteConfig = apps.get_model("tracker", "SiteConfig")
    for config in SiteConfig.objects.all():
        changed = []
        if (config.privacy_text or "").strip() == legal.OLD_PRIVACY.strip():
            config.privacy_text = legal.PRIVACY
            changed.append("privacy_text")
        if (config.terms_text or "").strip() == legal.OLD_TERMS.strip():
            config.terms_text = legal.TERMS
            changed.append("terms_text")
        if changed:
            config.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("tracker", "0036_legal_templates")]
    operations = [migrations.RunPython(upgrade, migrations.RunPython.noop)]
