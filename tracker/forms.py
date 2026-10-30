import re
import time
from urllib.parse import urlparse

from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms
from django.conf import settings
from django.core import signing

from .models import (
    Application, Contact, Interview, JobSource, KnowledgeSource, Offer, PersonalSettings, Referral, SavedSearch, SearchArea, UserProfile,
)
from .services import abuse, geo, knowledge
from .services.netguard import FetchError, check_public_url

SIGNUP_SALT = abuse.SIGNUP_SALT  # kept for older imports
SIGNUP_MAX_AGE = 2 * 24 * 3600  # a sign-up page left open longer than this has to be reloaded
PUBLIC_TOOL_SALT = "tracker.public-tool"


class HoneypotMixin(forms.Form):
    """Same bot protection as the sign-up form, for the public tools nobody needs an account to use: a text box
    real people never see, and a signed timestamp so a form submitted faster than a person could type it is refused."""

    website = forms.CharField(required=False, label="Leave this empty", widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))
    form_started = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["form_started"] = signing.dumps(time.time(), salt=PUBLIC_TOOL_SALT)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("Something went wrong. Please reload the page and try again.")
        minimum = settings.STILLOPEN_PUBLIC_TOOL_MIN_SECONDS
        if minimum > 0:
            try:
                started = signing.loads(cleaned.get("form_started") or "", salt=PUBLIC_TOOL_SALT, max_age=SIGNUP_MAX_AGE)
            except signing.BadSignature:
                raise forms.ValidationError("This page expired. Please reload it and try again.") from None
            if time.time() - started < minimum:
                raise forms.ValidationError("That was very quick. Please check your details and press the button again.")
        return cleaned


class JobFitToolForm(HoneypotMixin):
    description = forms.CharField(label="The job description", widget=forms.Textarea(attrs={"rows": 10}))
    cv = forms.CharField(label="Your CV or a summary of your skills and experience", widget=forms.Textarea(attrs={"rows": 10}))


class LivenessToolForm(HoneypotMixin):
    url = forms.URLField(label="Link to the job posting", max_length=600)


class OfferToolForm(HoneypotMixin):
    PERIODS = Offer.PERIODS

    a_label = forms.CharField(label="First offer's name", max_length=60, required=False, initial="Offer A")
    a_base = forms.DecimalField(label="Base pay", min_value=0, max_digits=12, decimal_places=2)
    a_period = forms.ChoiceField(label="Paid", choices=PERIODS, initial="year")
    a_currency = forms.CharField(label="Currency", max_length=3, initial="USD")
    a_bonus = forms.DecimalField(label="Yearly bonus", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    a_equity = forms.DecimalField(label="Yearly value of shares or options", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    a_signing = forms.DecimalField(label="One-off signing bonus", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    a_other_benefits = forms.DecimalField(label="Other yearly benefits worth counting", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)

    b_label = forms.CharField(label="Second offer's name", max_length=60, required=False, initial="Offer B")
    b_base = forms.DecimalField(label="Base pay", min_value=0, max_digits=12, decimal_places=2)
    b_period = forms.ChoiceField(label="Paid", choices=PERIODS, initial="year")
    b_currency = forms.CharField(label="Currency", max_length=3, initial="USD")
    b_bonus = forms.DecimalField(label="Yearly bonus", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    b_equity = forms.DecimalField(label="Yearly value of shares or options", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    b_signing = forms.DecimalField(label="One-off signing bonus", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    b_other_benefits = forms.DecimalField(label="Other yearly benefits worth counting", min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)

    def offers(self) -> list[Offer]:
        """Two unsaved Offer instances -- never written to the database, just reused for the same per-currency math.
        `.label` is set as a plain attribute (not a model field) so the template can show each offer's own name."""
        out = []
        for side, default in (("a", "Offer A"), ("b", "Offer B")):
            data = self.cleaned_data
            offer = Offer(
                base=data[f"{side}_base"], period=data[f"{side}_period"], currency=(data[f"{side}_currency"] or "USD").strip().upper()[:3],
                bonus=data[f"{side}_bonus"] or 0, equity=data[f"{side}_equity"] or 0, signing=data[f"{side}_signing"] or 0,
                other_benefits=data[f"{side}_other_benefits"] or 0,
            )
            offer.label = (data[f"{side}_label"] or "").strip() or default
            out.append(offer)
        return out


class SignupForm(AllauthSignupForm):
    """Sign-up with two invisible bot traps and no third-party service: a text box real people never see (bots fill every box),
    and a signed timestamp so a form sent faster than a person could type it, or replayed from another day, is refused.

    A bot is never told why: if it fills the trap or is too fast, it gets the same "check your email" page as everyone and no
    account is made (`try_save`). A person whose page simply went stale is told to reload it. The switch and the numbers are in
    the admin (Site configuration > Registration); see services/abuse.py."""

    website = forms.CharField(required=False, label="Leave this empty", widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off", "aria-hidden": "true"}))
    form_started = forms.CharField(required=False, widget=forms.HiddenInput)

    suspected_bot = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["form_started"] = abuse.make_signup_token()

    def clean(self):
        cleaned = super().clean()
        self.suspected_bot = False
        if not abuse.signup_protection_on():
            return cleaned
        if cleaned.get("website"):
            self.suspected_bot = True
        minimum = abuse.signup_min_seconds()
        if minimum > 0:
            token = cleaned.get("form_started") or ""
            started = abuse.read_signup_token(token)
            if started is None:  # missing, tampered with, or older than the allowed age: a person needs to reload the page
                raise forms.ValidationError("This page expired. Please reload it and try again.")
            if time.time() - started < minimum or abuse.token_already_used(token):
                self.suspected_bot = True
        return cleaned

    def try_save(self, request):
        if self.suspected_bot:
            from allauth.account.adapter import get_adapter

            return None, get_adapter().respond_email_verification_sent(request, None)  # looks like success; nothing was created
        user, response = super().try_save(request)
        if user is not None:
            abuse.mark_token_used(self.cleaned_data.get("form_started") or "")
        return user, response


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
            "notice_period", "salary_floor", "deal_breakers", "about", "profile_cv", "scan_digest_enabled", "draft_ahead_enabled", "weekly_digest_enabled", "timezone",
            "email_followups", "email_interviews", "email_weekly",
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

    open_remote = forms.BooleanField(
        required=False, initial=True, label="I am happy to work remotely, from anywhere",
        help_text="Untick if you only want work in a place you name below.",
    )
    other_places = forms.CharField(
        required=False, max_length=600, label="Anywhere else you would work in person?",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Malaysia\nGulf"}),
        help_text="A country like Malaysia, or a region like Gulf or Europe, one per line. Leave it empty to look only where you live, plus remote.",
    )

    class Meta(ProfileForm.Meta):
        fields = ["target_roles", "home_country", "profile_cv"]
        labels = {"profile_cv": "Or paste your CV here"}

    def clean_other_places(self):
        lines = [line.strip() for line in (self.cleaned_data.get("other_places") or "").splitlines() if line.strip()]
        if len(lines) > 8:
            raise forms.ValidationError("That is a lot of places. Name up to 8 here; you can add more in your profile later.")
        if any(len(line) > 80 for line in lines):
            raise forms.ValidationError("Each place should be a short name, one per line.")
        return "\n".join(lines)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("employment_types", "seniority_levels"):
            self.fields.pop(name, None)
        self.order_fields(["target_roles", "home_country", "open_remote", "other_places", "cv_file", "profile_cv"])
        self.fields["target_roles"].label = "What kind of work are you looking for?"
        self.fields["target_roles"].help_text = "One role per line. It is fine to be rough, you can change it any time."
        self.fields["home_country"].label = "Where do you live?"
        self.fields["home_country"].help_text = "So we can tell you whether a job is open to someone there. A country name is enough."
        self.fields["cv_file"].label = "Your CV"
        self.fields["cv_file"].help_text = "PDF, .txt or .md. We read the text and keep that, not the file."


MAX_AREAS = 20


def create_default_areas(user, home_country: str, open_remote: bool, other_places: str) -> int:
    """Turn the welcome answers into visible, editable search areas. Only for someone who has none yet, so a person's own
    careful setup is never replaced. Where they live: any kind of work. Remote anywhere: remote only. Other places: in person
    or hybrid. Returns how many rows were made."""
    if user.search_areas.exists():
        return 0
    rows = []
    if home_country:
        rows.append({"place": geo.country_name(home_country), "allow_remote": True, "allow_hybrid": True, "allow_onsite": True})
    if open_remote:
        rows.append({"place": "Anywhere", "allow_remote": True})
    for line in (other_places or "").splitlines():
        line = line.strip()
        if line and line.lower() not in {r["place"].lower() for r in rows}:
            rows.append({"place": line[:80], "allow_remote": True, "allow_hybrid": True, "allow_onsite": True})
    for position, row in enumerate(rows[:MAX_AREAS]):
        SearchArea.objects.create(owner=user, order=position, **row)
    return len(rows[:MAX_AREAS])


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


# --- pipeline after "Applied": interviews, contacts and referrals, offers ------------------------------

class OwnedFormMixin:
    """Every foreign key a person can pick (a job, a contact) is limited to their own rows, so a forged id is an invalid choice."""

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        if "application" in self.fields:
            self.fields["application"].queryset = Application.objects.filter(owner=owner).order_by("company", "role")
            self.fields["application"].label_from_instance = lambda a: f"{a.company} - {a.role}"
        if "contact" in self.fields:
            self.fields["contact"].queryset = Contact.objects.filter(owner=owner)
        if "contacts" in self.fields:
            self.fields["contacts"].queryset = Contact.objects.filter(owner=owner)


class InterviewForm(OwnedFormMixin, forms.ModelForm):
    scheduled_at = forms.DateTimeField(
        label="When", input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        help_text="In your own time zone.",
    )

    class Meta:
        model = Interview
        fields = ["application", "scheduled_at", "kind", "custom_label", "where", "notes", "contacts"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
        labels = {"where": "Where or link", "custom_label": "Name of this stage (optional)", "contacts": "Who interviewed you"}


class ContactForm(OwnedFormMixin, forms.ModelForm):
    last_contacted = forms.DateField(required=False, label="Last spoke", widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Contact
        fields = ["name", "company", "title", "email", "link", "last_contacted", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class SavedSearchForm(forms.ModelForm):
    class Meta:
        model = SavedSearch
        fields = ["name", "target_roles", "enabled"]
        widgets = {"target_roles": forms.Textarea(attrs={"rows": 4})}
        labels = {"name": "Name", "target_roles": "Roles (one per line)"}

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Give this search a name.")
        clash = SavedSearch.objects.filter(owner=self.owner, name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have a saved search with this name.")
        return name

    def clean_target_roles(self):
        roles = self.cleaned_data["target_roles"].strip()
        if not roles:
            raise forms.ValidationError("Add at least one role.")
        return roles


class ReferralForm(OwnedFormMixin, forms.ModelForm):
    class Meta:
        model = Referral
        fields = ["contact", "application", "status", "note"]


class OfferForm(OwnedFormMixin, forms.ModelForm):
    deadline = forms.DateField(required=False, label="Reply by", widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Offer
        fields = ["application", "base", "period", "currency", "bonus", "equity", "other_benefits", "signing", "deadline", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def clean_currency(self):
        value = (self.cleaned_data.get("currency") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise forms.ValidationError("Use a three-letter code such as USD, BDT or MYR.")
        return value


# --- a person's own company job boards ---------------------------------------------------------------

_OWN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}")
_BOARD_HOSTS = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "ashby": ("jobs.ashbyhq.com",),
    "smartrecruiters": ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"),
}


def board_token_from(connector: str, raw: str) -> str:
    """Accept the token itself, or a careers-page address pasted from the browser. Only text is parsed: the pasted
    address is never fetched, and only the token is kept (the app always builds the real URL itself)."""
    raw = (raw or "").strip()
    if not raw.lower().startswith(("http://", "https://")):
        return raw
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if connector == "recruitee" and host.endswith(".recruitee.com"):
        return host[: -len(".recruitee.com")]
    if host in _BOARD_HOSTS.get(connector, ()):
        return next((p for p in parsed.path.split("/") if p), "")
    return ""


class OwnSourceForm(forms.Form):
    connector = forms.ChoiceField(
        choices=[(c, label) for c, label in JobSource.CONNECTORS if c in JobSource.OWN_CONNECTORS],
        label="Which hiring system does the company use?",
        help_text="Check the address of the company's careers page: boards.greenhouse.io/..., jobs.lever.co/..., jobs.ashbyhq.com/..., jobs.smartrecruiters.com/... or ....recruitee.com.",
    )
    board_token = forms.CharField(
        max_length=300, label="The company's name in that address, or paste the careers page address",
        help_text="For jobs.lever.co/acme the name is acme.",
    )
    name = forms.CharField(max_length=120, required=False, label="Company name (optional)", help_text="Shown in your search log. Defaults to the name from the address.")

    def clean(self):
        cleaned = super().clean()
        connector = cleaned.get("connector")
        if not connector or "board_token" not in cleaned:
            return cleaned
        if connector == "careerpage":
            from tracker.services import careerpage
            try:
                url = careerpage.normalise_url(cleaned["board_token"])
                check_public_url(url)
            except ValueError as exc:
                self.add_error("board_token", str(exc))
                return cleaned
            except FetchError:
                self.add_error("board_token", "That address is not a public website.")
                return cleaned
            cleaned["board_token"] = url
            cleaned["name"] = (cleaned.get("name") or "").strip() or (urlparse(url).hostname or "")[:120]
            return cleaned
        token = board_token_from(connector, cleaned["board_token"])
        if not _OWN_TOKEN.fullmatch(token):
            self.add_error("board_token", "That does not look like a company name from a careers page address. Use letters, digits, dash or underscore only, or paste the careers page address.")
        else:
            cleaned["board_token"] = token
            cleaned["name"] = (cleaned.get("name") or "").strip() or token
        return cleaned
