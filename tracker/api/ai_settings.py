"""AI settings for the new app. Keys are write-only: nothing here ever returns a key, only whether one is saved. The classic page's form does
the checking, so a restricted (non-staff) person still cannot choose a command-line provider or a local or private address."""
from django.db.models import Count, Sum
from django.utils import timezone
from ninja import Router

from .. import forms
from ..models import AIUsageEvent, UserProfile
from .account import merged, read_payload
from .common import validate_form

router = Router()

# Known OpenAI-compatible endpoints (the same list the classic page fills in with JavaScript). Model names on fast-moving providers drift, so
# these are safe starting picks, and the model field stays editable. `staff_only` ones point at this server's own machine.
PRESETS = [
    {"key": "gemini", "label": "Google AI Studio (Gemini): free key, easiest start", "provider": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash", "staff_only": False},
    {"key": "anthropic", "label": "Anthropic (Claude), direct", "provider": "anthropic", "base_url": "", "model": "", "staff_only": False},
    {"key": "openai", "label": "OpenAI", "provider": "openai", "base_url": "", "model": "gpt-4o-mini", "staff_only": False},
    {"key": "groq", "label": "Groq", "provider": "openai", "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b", "staff_only": False},
    {"key": "mistral", "label": "Mistral", "provider": "openai", "base_url": "https://api.mistral.ai/v1", "model": "mistral-small-latest", "staff_only": False},
    {"key": "deepseek", "label": "DeepSeek", "provider": "openai", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash", "staff_only": False},
    {"key": "openrouter", "label": "OpenRouter (routes to many models)", "provider": "openai", "base_url": "https://openrouter.ai/api/v1", "model": "openrouter/auto", "staff_only": False},
    {"key": "glm", "label": "GLM / Zhipu AI (z.ai)", "provider": "openai", "base_url": "https://api.z.ai/api/paas/v4", "model": "glm-4.6", "staff_only": False},
    {"key": "ollama", "label": "Ollama: local, free, this server only", "provider": "openai", "base_url": "http://127.0.0.1:11434/v1", "model": "llama3", "staff_only": True},
    {"key": "lmstudio", "label": "LM Studio: local, free, this server only", "provider": "openai", "base_url": "http://127.0.0.1:1234/v1", "model": "", "staff_only": True},
]

FIELDS = [
    "ai_provider", "ai_model", "ai_base_url", "ai_custom_headers", "ai_custom_body", "ai_custom_response_path", "ai_timeout", "ai_max_input_chars",
    "rag_enabled", "rag_mode", "rag_top_k", "rag_chunk_chars", "rag_always_chars", "rag_embedding_base_url", "rag_embedding_model",
]


def _usage(user) -> dict:
    now = timezone.localtime()
    month = AIUsageEvent.objects.filter(owner=user, created_at__year=now.year, created_at__month=now.month)
    total = month.aggregate(input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"), cost_usd=Sum("cost_usd"), calls=Count("id"))
    return {
        "calls": total["calls"], "total_tokens": (total["input_tokens"] or 0) + (total["output_tokens"] or 0),
        "cost_usd": float(total["cost_usd"]) if total["cost_usd"] else None,
        "any_estimated": month.filter(cost_is_estimate=True, cost_usd__isnull=False).exists(),
    }


def _settings_json(user) -> dict:
    profile = UserProfile.for_user(user)
    form = forms.AISettingsForm(instance=profile, restricted=not user.is_staff)
    return {
        "settings": {name: getattr(profile, name) for name in FIELDS},
        "has_key": bool(profile.ai_key_encrypted),  # only whether a key is saved, never the key
        "has_rag_key": bool(profile.rag_embedding_key_encrypted),
        "providers": [{"value": value, "label": label} for value, label in form.fields["ai_provider"].choices],
        "rag_modes": [{"value": value, "label": label} for value, label in UserProfile.RAG_MODES],
        "presets": [{k: v for k, v in p.items() if k != "staff_only"} for p in PRESETS if user.is_staff or not p["staff_only"]],
        "provider_label": "" if profile.ai_provider == "none" else f"{profile.get_ai_provider_display()}{' (' + profile.ai_model + ')' if profile.ai_model else ''}",
        "usage": _usage(user),
        "limits": {
            "ai_timeout": [10, 180], "ai_max_input_chars": [1000, 30000], "rag_top_k": [1, 12], "rag_chunk_chars": [300, 3000], "rag_always_chars": [0, 5000],
        },
    }


@router.get("/ai-settings", summary="The person's AI settings (never any key)")
def get_settings(request):
    return _settings_json(request.user)


@router.put("/ai-settings", summary="Save the AI settings; a key is write-only and a blank key keeps the saved one")
def save_settings(request):
    data, _ = read_payload(request)
    obj = UserProfile.for_user(request.user)
    restricted = not request.user.is_staff
    form = forms.AISettingsForm(merged(forms.AISettingsForm(instance=obj, restricted=restricted), data), instance=obj, restricted=restricted)
    validate_form(form)
    form.save()
    return _settings_json(request.user)
