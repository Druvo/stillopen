from django.conf import settings
from django.db import migrations

PER_USER = [
    "ai_provider", "ai_model", "ai_base_url", "ai_custom_headers", "ai_custom_body", "ai_custom_response_path",
    "ai_claude_command", "ai_timeout", "ai_max_input_chars", "ai_key_encrypted", "profile_cv",
    "rag_enabled", "rag_mode", "rag_top_k", "rag_chunk_chars", "rag_always_chars",
    "rag_embedding_base_url", "rag_embedding_model", "rag_embedding_key_encrypted",
]


def assign(apps, schema_editor):
    """Single-user installs: the existing jobs, documents and settings become the first admin's."""
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    owner = User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()
    if owner is None:
        return  # nobody to give it to yet; tracker.services.claim does it when the first user is created
    for name in ("Application", "KnowledgeSource", "LivenessRun"):
        apps.get_model("tracker", name).objects.filter(owner__isnull=True).update(owner=owner)
    SiteConfig = apps.get_model("tracker", "SiteConfig")
    UserProfile = apps.get_model("tracker", "UserProfile")
    config = SiteConfig.objects.filter(pk=1).first()
    if config and not UserProfile.objects.filter(user=owner).exists():
        values = {name: getattr(config, name) for name in PER_USER}
        UserProfile.objects.create(user=owner, about=config.profile_preferences, **values)


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0009_multi_user"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
