from django import forms

from .models import Application, KnowledgeSource, PersonalSettings, UserProfile
from .services import knowledge
from .services.netguard import FetchError, check_public_url

RESTRICTED_PROVIDERS = {"claude_cli", "agent_sdk"}  # these run commands on the server: site admins only


class SecretKeysMixin(forms.Form):
    """Write-only API key fields: encrypted on save, never rendered back."""

    ai_api_key = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}), label="AI API key",
        help_text="Stored encrypted and never shown again. Leave blank to keep the saved key.",
    )
    clear_ai_key = forms.BooleanField(required=False, label="Delete the saved AI key")
    rag_embedding_key = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}), label="Embeddings API key",
        help_text="Optional. If empty, your AI key is used for embeddings too.",
    )
    clear_rag_key = forms.BooleanField(required=False, label="Delete the saved embeddings key")

    def apply_secrets(self, instance) -> None:
        if self.cleaned_data.get("clear_ai_key"):
            instance.ai_key_encrypted = ""
        elif self.cleaned_data.get("ai_api_key"):
            instance.set_ai_key(self.cleaned_data["ai_api_key"])
        if self.cleaned_data.get("clear_rag_key"):
            instance.rag_embedding_key_encrypted = ""
        elif self.cleaned_data.get("rag_embedding_key"):
            instance.set_rag_key(self.cleaned_data["rag_embedding_key"])


class AISettingsForm(SecretKeysMixin, forms.ModelForm):
    """A person's AI provider, retrieval settings and keys. Ordinary users get the safe provider list and public URLs only."""

    class Meta:
        model = UserProfile
        fields = [
            "ai_provider", "ai_model", "ai_base_url", "ai_custom_headers", "ai_custom_body", "ai_custom_response_path",
            "ai_timeout", "ai_max_input_chars",
            "rag_enabled", "rag_mode", "rag_top_k", "rag_chunk_chars", "rag_always_chars",
            "rag_embedding_base_url", "rag_embedding_model",
        ]
        widgets = {"ai_custom_headers": forms.Textarea(attrs={"rows": 3}), "ai_custom_body": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, restricted: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.restricted = restricted
        if restricted:
            self.fields["ai_provider"].choices = [c for c in PersonalSettings.AI_PROVIDERS if c[0] not in RESTRICTED_PROVIDERS]
        for name, low, high in [("ai_timeout", 10, 180), ("ai_max_input_chars", 1000, 30000), ("rag_top_k", 1, 12),
                                ("rag_chunk_chars", 300, 3000), ("rag_always_chars", 0, 5000)]:
            self.fields[name].widget.attrs.update(min=low, max=high)

    def _bounded(self, name, low, high):
        value = self.cleaned_data.get(name)
        if value is not None and not low <= value <= high:
            raise forms.ValidationError(f"Use a number between {low} and {high}.")
        return value

    def clean_ai_timeout(self):
        return self._bounded("ai_timeout", 10, 180)

    def clean_ai_max_input_chars(self):
        return self._bounded("ai_max_input_chars", 1000, 30000)

    def clean_rag_top_k(self):
        return self._bounded("rag_top_k", 1, 12)

    def clean_rag_chunk_chars(self):
        return self._bounded("rag_chunk_chars", 300, 3000)

    def clean_rag_always_chars(self):
        return self._bounded("rag_always_chars", 0, 5000)

    def _check_url(self, field):
        url = (self.cleaned_data.get(field) or "").strip()
        if not url:
            return url
        if not url.startswith(("http://", "https://")):
            raise forms.ValidationError("Use a full URL starting with https://")
        if self.restricted:
            try:
                check_public_url(url)
            except FetchError as exc:
                raise forms.ValidationError(f"{exc} Local and private addresses are not allowed on this server.") from exc
        return url

    def clean_ai_base_url(self):
        return self._check_url("ai_base_url")

    def clean_rag_embedding_base_url(self):
        return self._check_url("rag_embedding_base_url")

    def save(self, commit=True):
        instance = super().save(commit=False)
        self.apply_secrets(instance)
        if commit:
            instance.save()
        return instance


class ProfileForm(forms.ModelForm):
    cv_file = forms.FileField(
        required=False, label="Upload your CV",
        help_text="PDF, .txt or .md, up to 2 MB. The text is read into the box below; the file itself is not kept.",
    )

    class Meta:
        model = UserProfile
        fields = ["target_roles", "locations", "remote_preference", "salary_floor", "deal_breakers", "about", "profile_cv"]
        widgets = {
            "target_roles": forms.Textarea(attrs={"rows": 3, "placeholder": "Senior Backend Engineer\nSolutions Architect"}),
            "locations": forms.Textarea(attrs={"rows": 2, "placeholder": "Dhaka\nRemote"}),
            "deal_breakers": forms.Textarea(attrs={"rows": 2}),
            "about": forms.Textarea(attrs={"rows": 3}),
            "profile_cv": forms.Textarea(attrs={"rows": 14}),
        }
        labels = {"profile_cv": "Your CV (text)"}

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("cv_file")
        if upload:
            try:
                cleaned["profile_cv"] = knowledge.extract_text(upload)
            except knowledge.KnowledgeError as exc:
                self.add_error("cv_file", str(exc))
        if len(cleaned.get("profile_cv") or "") > knowledge.MAX_TEXT_CHARS:
            self.add_error("profile_cv", "That CV text is too long.")
        return cleaned


class JobForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["company", "role", "url", "deadline", "description", "notes"]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 10, "placeholder": "Paste the job description. Leave blank to fetch it from the link."}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_description(self):
        text = self.cleaned_data.get("description", "")
        if len(text) > 30000:
            raise forms.ValidationError("That description is longer than 30,000 characters.")
        return text


class KnowledgeForm(forms.ModelForm):
    class Meta:
        model = KnowledgeSource
        fields = ["title", "kind", "text", "file"]
        widgets = {"text": forms.Textarea(attrs={"rows": 8})}
        labels = {"file": "Or upload a file"}

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("file")
        if upload and not (cleaned.get("text") or "").strip():
            try:
                cleaned["text"] = knowledge.extract_text(upload)
            except knowledge.KnowledgeError as exc:
                self.add_error("file", str(exc))
        if not (cleaned.get("text") or "").strip() and not self.errors:
            self.add_error("text", "Add some text or upload a file.")
        if len(cleaned.get("text") or "") > knowledge.MAX_TEXT_CHARS:
            self.add_error("text", "That text is too long.")
        return cleaned
