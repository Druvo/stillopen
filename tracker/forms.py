import re
import time

from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
from django.conf import settings
from django.core import signing
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory

from .models import Application, KnowledgeSource, PersonalSettings, SearchArea, UserProfile
from .services import geo, knowledge
from .services.netguard import FetchError, check_public_url

SIGNUP_SALT = "tracker.signup-form"
SIGNUP_MAX_AGE = 2 * 24 * 3600  # a sign-up page left open longer than this has to be reloaded


class SignupForm(AllauthSignupForm):
    """Sign-up with two invisible bot traps and no third-party service: a text box real people never see (bots fill
    every box), and a signed timestamp so a form submitted faster than a person could type it is refused."""

    website = forms.CharField(required=False, label="Leave this empty", widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))
    form_started = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["form_started"] = signing.dumps(time.time(), salt=SIGNUP_SALT)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("We could not create this account. Please try again.")
        minimum = settings.STILLOPEN_SIGNUP_MIN_SECONDS
        if minimum > 0:
            try:
                started = signing.loads(cleaned.get("form_started") or "", salt=SIGNUP_SALT, max_age=SIGNUP_MAX_AGE)
            except signing.BadSignature:
                raise forms.ValidationError("This page expired. Please reload it and try again.") from None
            if time.time() - started < minimum:
                raise forms.ValidationError("That was very quick. Please check your details and press the button again.")
        return cleaned


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
    home_country = forms.CharField(
        required=False, max_length=60, label="The country you live in",
        help_text="A name like Bangladesh or a code like BD. Remote jobs limited to one country only fit you if it is this one.",
    )
    employment_types = forms.MultipleChoiceField(
        required=False, choices=UserProfile.EMPLOYMENT, widget=forms.CheckboxSelectMultiple,
        label="Kinds of employment you want", help_text="Leave all unticked for no preference.",
    )
    seniority_levels = forms.MultipleChoiceField(
        required=False, choices=UserProfile.SENIORITY, widget=forms.CheckboxSelectMultiple,
        label="Seniority you want", help_text="Leave all unticked for no preference.",
    )

    class Meta:
        model = UserProfile
        fields = [
            "target_roles", "home_country", "employment_types", "seniority_levels", "industries", "languages",
            "notice_period", "salary_floor", "deal_breakers", "about", "profile_cv", "scan_digest_enabled",
        ]
        widgets = {
            "target_roles": forms.Textarea(attrs={"rows": 3, "placeholder": "Senior Backend Engineer\nSolutions Architect"}),
            "industries": forms.Textarea(attrs={"rows": 2, "placeholder": "Fintech\nE-commerce"}),
            "languages": forms.Textarea(attrs={"rows": 2, "placeholder": "English\nBangla"}),
            "deal_breakers": forms.Textarea(attrs={"rows": 2}),
            "about": forms.Textarea(attrs={"rows": 3}),
            "profile_cv": forms.Textarea(attrs={"rows": 14}),
        }
        labels = {"profile_cv": "Your CV (text)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.home_country:
            self.initial["home_country"] = geo.country_name(self.instance.home_country)

    def clean_home_country(self):
        value = (self.cleaned_data.get("home_country") or "").strip()
        if not value:
            return ""
        if len(value) == 2 and value.upper() in geo.COUNTRIES:
            return value.upper()
        codes = geo.resolve_place(value)
        if codes and len(codes) == 1 and "*" not in codes:
            return next(iter(codes))
        raise forms.ValidationError("Not recognised as one country. Use a name like Bangladesh or a code like BD.")

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


class WelcomeForm(ProfileForm):
    """The three things worth asking a new person: what they want, where they live, their CV."""

    class Meta(ProfileForm.Meta):
        fields = ["target_roles", "home_country", "profile_cv"]
        labels = {"profile_cv": "Or paste your CV here"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("employment_types", "seniority_levels"):
            self.fields.pop(name, None)
        self.order_fields(["target_roles", "home_country", "cv_file", "profile_cv"])
        self.fields["target_roles"].label = "What kind of work are you looking for?"
        self.fields["target_roles"].help_text = "One role per line. It is fine to be rough, you can change it any time."
        self.fields["home_country"].label = "Where do you live?"
        self.fields["home_country"].help_text = "So we can tell you whether a job is open to someone there. A country name is enough."
        self.fields["cv_file"].label = "Your CV"
        self.fields["cv_file"].help_text = "PDF, .txt or .md. We read the text and keep that, not the file."


MAX_AREAS = 20


class SearchAreaForm(forms.ModelForm):
    class Meta:
        model = SearchArea
        fields = [
            "place", "city", "allow_remote", "allow_hybrid", "allow_onsite", "needs_visa_sponsorship",
            "needs_relocation_support", "min_salary", "salary_currency", "salary_period",
        ]
        widgets = {"salary_currency": forms.TextInput(attrs={"size": 4, "maxlength": 3, "placeholder": "USD"})}

    unrecognised = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["salary_period"].required = False

    @property
    def changed_data(self):
        # The pay period always has a default, so a row nobody touched must not count as filled in.
        return [name for name in super().changed_data if name != "salary_period"]

    def clean_salary_period(self):
        return self.cleaned_data.get("salary_period") or "month"

    def clean_place(self):
        place = (self.cleaned_data.get("place") or "").strip()
        if place and geo.resolve_place(place) is None:
            self.unrecognised = True  # allowed, but matched by name only; the page says so
        return place

    def clean_salary_currency(self):
        return (self.cleaned_data.get("salary_currency") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("place"):
            return cleaned
        if not (cleaned.get("allow_remote") or cleaned.get("allow_hybrid") or cleaned.get("allow_onsite")):
            self.add_error(None, "Choose at least one of remote, hybrid or on-site for this place.")
        if cleaned.get("min_salary") and not cleaned.get("salary_currency"):
            self.add_error("salary_currency", "Add the currency for this minimum (e.g. USD).")
        if cleaned.get("salary_currency") and not re.fullmatch(r"[A-Z]{3}", cleaned["salary_currency"]):
            self.add_error("salary_currency", "Use a 3-letter code such as USD or BDT.")
        return cleaned


class BaseAreaFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        live = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("place")]
        if len(live) > MAX_AREAS:
            raise forms.ValidationError(f"You can have at most {MAX_AREAS} search areas.")

    @property
    def unrecognised_places(self) -> list[str]:
        return [f.cleaned_data["place"] for f in self.forms if getattr(f, "unrecognised", False) and f.cleaned_data.get("place")]


SearchAreaFormSet = inlineformset_factory(
    get_user_model(), SearchArea, form=SearchAreaForm, formset=BaseAreaFormSet, fk_name="owner",
    extra=2, can_delete=True, max_num=MAX_AREAS + 5,
)


def save_areas(formset, user) -> None:
    """Save the rows in the order they appear on the page."""
    formset.save(commit=False)
    for obj in formset.deleted_objects:
        obj.delete()
    kept = [f.instance for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("place")]
    for position, obj in enumerate(kept):
        obj.owner = user
        obj.order = position
        obj.save()


class JobForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["company", "role", "url", "deadline", "description", "notes"]
        labels = {
            "url": "Link to the posting", "deadline": "Apply by (if it says)", "description": "The job description",
            "notes": "Your own notes",
        }
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 10, "placeholder": "Paste the text of the posting here. Or leave this empty and we will read it from the link."}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_description(self):
        text = self.cleaned_data.get("description", "")
        if len(text) > 30000:
            raise forms.ValidationError("That description is longer than 30,000 characters.")
        return text


class JobEditForm(forms.ModelForm):
    """Everything about one job the person may correct, including where it is and what kind of role it is."""

    country = forms.CharField(
        required=False, max_length=60, label="Country (where you must be based)",
        help_text="A name like Malaysia or a code like MY. Leave blank if the posting does not say, or for remote work open worldwide.",
    )

    class Meta:
        model = Application
        fields = [
            "company", "role", "url", "deadline", "location_text", "country", "arrangement", "sponsorship", "relocation",
            "employment_type", "seniority", "advertised_pay", "description", "notes",
        ]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 10}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.country:
            self.initial["country"] = geo.country_name(self.instance.country)

    def clean_country(self):
        value = (self.cleaned_data.get("country") or "").strip()
        if not value:
            return ""
        if len(value) == 2 and value.upper() in geo.COUNTRIES:
            return value.upper()
        codes = geo.resolve_place(value)
        if codes and len(codes) == 1 and "*" not in codes:
            return next(iter(codes))
        raise forms.ValidationError("Not recognised as one country. Use a name like Malaysia or a code like MY.")

    def clean_description(self):
        text = self.cleaned_data.get("description", "")
        if len(text) > 30000:
            raise forms.ValidationError("That description is longer than 30,000 characters.")
        return text

    def save(self, commit=True):
        job = super().save(commit=False)
        detail_fields = {"location_text", "country", "arrangement", "sponsorship", "relocation", "employment_type", "seniority"}
        if detail_fields & set(self.changed_data):
            job.details_source = "manual"  # the person has spoken: detection will not overwrite these
        if commit:
            job.save()
        return job


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
