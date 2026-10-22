import os
from datetime import date
from urllib.parse import urlparse

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from . import crypto

# Settings that belong to one person. SiteConfig holds legacy values (used to seed the first user);
# every request works with SiteConfig.for_user(user), which overlays the person's own profile.
PER_USER_FIELDS = [
    "ai_provider", "ai_model", "ai_base_url", "ai_custom_headers", "ai_custom_body", "ai_custom_response_path",
    "ai_claude_command", "ai_timeout", "ai_max_input_chars", "ai_key_encrypted", "profile_cv",
    "rag_enabled", "rag_mode", "rag_top_k", "rag_chunk_chars", "rag_always_chars",
    "rag_embedding_base_url", "rag_embedding_model", "rag_embedding_key_encrypted",
]


class PersonalSettings(models.Model):
    """Fields and helpers shared by SiteConfig (legacy/default) and UserProfile (per person)."""

    AI_PROVIDERS = [
        ("none", "Off (free keyword match only)"),
        ("anthropic", "Anthropic API key"),
        ("openai", "OpenAI-compatible API (OpenAI, OpenRouter, Groq, Mistral, Gemini, DeepSeek, Ollama, LM Studio...)"),
        ("custom_http", "Custom HTTP API (any provider: you describe the request and where the answer is)"),
        ("claude_cli", "Claude Code CLI installed on this machine (site admins only)"),
        ("agent_sdk", "Claude Agent SDK (site admins only; pip install -r requirements-ai.txt)"),
    ]
    RAG_MODES = [
        ("lexical", "Keyword ranking (BM25): free, works offline, nothing extra leaves your machine"),
        ("embeddings", "Embeddings: better at meaning, sends your text chunks to an embeddings API"),
    ]

    ai_provider = models.CharField(max_length=12, choices=AI_PROVIDERS, default="none")
    ai_model = models.CharField(max_length=100, blank=True, help_text="Leave blank for the provider's default.")
    ai_base_url = models.CharField(
        max_length=300,
        blank=True,
        help_text=(
            "OpenAI-compatible: the API base, e.g. https://openrouter.ai/api/v1, https://api.groq.com/openai/v1, "
            "https://api.mistral.ai/v1, https://generativelanguage.googleapis.com/v1beta/openai (Gemini), "
            "http://127.0.0.1:11434/v1 (Ollama, site admins only). Custom HTTP: the full endpoint URL."
        ),
    )
    ai_custom_headers = models.TextField(
        blank=True,
        help_text="Custom HTTP only. One header per line, e.g. 'Authorization: Bearer {{api_key}}' or 'x-api-key: {{api_key}}'.",
    )
    ai_custom_body = models.TextField(
        blank=True,
        help_text=(
            "Custom HTTP only. JSON request body. Use {{system}}, {{prompt}} and {{model}} where the text goes, "
            'e.g. {"model": "{{model}}", "messages": [{"role": "system", "content": "{{system}}"}, '
            '{"role": "user", "content": "{{prompt}}"}]}'
        ),
    )
    ai_custom_response_path = models.CharField(
        max_length=200,
        blank=True,
        help_text="Custom HTTP only. Where the reply text is in the JSON response, e.g. choices.0.message.content or content.0.text",
    )
    ai_claude_command = models.CharField(max_length=200, default="claude", help_text="Claude Code CLI command or full path.")
    ai_timeout = models.PositiveIntegerField(default=120, help_text="Seconds to wait for one evaluation.")
    ai_max_input_chars = models.PositiveIntegerField(
        default=12000, help_text="Job descriptions longer than this are cut before being sent to the AI."
    )
    ai_key_encrypted = models.TextField(blank=True, editable=False)
    profile_cv = models.TextField(
        blank=True,
        help_text="Your CV as plain text. Sent to the AI provider you choose.",
    )

    rag_enabled = models.BooleanField(
        default=True,
        help_text="Send the AI only the parts of your CV and knowledge sources that are relevant to each job, instead of the whole CV.",
    )
    rag_mode = models.CharField(max_length=10, choices=RAG_MODES, default="lexical")
    rag_top_k = models.PositiveIntegerField(default=6, help_text="How many passages to retrieve per job.")
    rag_chunk_chars = models.PositiveIntegerField(default=900, help_text="Target size of one passage.")
    rag_always_chars = models.PositiveIntegerField(
        default=1500, help_text="The opening of your CV (summary, headline) is always included, up to this many characters."
    )
    rag_embedding_base_url = models.CharField(
        max_length=300,
        blank=True,
        help_text="Embeddings mode: OpenAI-compatible base URL, e.g. https://api.openai.com/v1. Blank = the AI base URL, then OpenAI.",
    )
    rag_embedding_model = models.CharField(
        max_length=100, blank=True, help_text="e.g. text-embedding-3-small, or nomic-embed-text for Ollama."
    )
    rag_embedding_key_encrypted = models.TextField(blank=True, editable=False)

    # True when these settings belong to an ordinary (non-staff) user on a shared server.
    # Such users may not point the server at private addresses or run local commands.
    restricted = False

    class Meta:
        abstract = True

    def set_rag_key(self, plain: str) -> None:
        self.rag_embedding_key_encrypted = crypto.encrypt(plain.strip())

    @property
    def effective_rag_key(self) -> str:
        """Embeddings key: its own, else the AI key (OpenAI-style providers use one key for both)."""
        return (
            os.environ.get("STILLOPEN_EMBEDDING_API_KEY", "").strip()
            or crypto.decrypt(self.rag_embedding_key_encrypted)
            or self.effective_ai_key
        )

    def set_ai_key(self, plain: str) -> None:
        self.ai_key_encrypted = crypto.encrypt(plain.strip())

    @property
    def effective_ai_key(self) -> str:
        return os.environ.get("STILLOPEN_AI_API_KEY", "").strip() or crypto.decrypt(self.ai_key_encrypted)

    @property
    def effective_profile_cv(self) -> str:
        if self.profile_cv.strip():
            return self.profile_cv
        folder = getattr(self, "careerops_path", "")
        if folder:
            cv = os.path.join(folder, "cv.md")
            if os.path.isfile(cv):
                with open(cv, encoding="utf-8") as fh:
                    return fh.read()
        return ""


DEFAULT_PRIVACY = """What we store: your account (email, username), the CV text and documents you add, your job preferences, and the jobs you track with their notes and evaluations. API keys you add are stored encrypted.

Who sees it: only you. Site administrators can access the database for maintenance.

AI features: only when you press Evaluate, the job description, your preferences and the relevant parts of your CV are sent to the AI provider you configured, using your own key. We do not send your data to any AI provider you have not chosen.

Your control: you can export all of your data and delete your account, with everything attached to it, from the Profile page at any time.

(Site owner: replace this text in the admin under Site configuration > Legal with your own policy, including who operates the service and how to contact you.)"""

DEFAULT_TERMS = """This service is provided as is. You are responsible for the content you add and for checking any job posting yourself before applying. The match percentages and summaries are automated estimates, not advice, and can be wrong.

(Site owner: replace this text in the admin under Site configuration > Legal.)"""


class SiteConfig(PersonalSettings):
    """Single-row site configuration, edited in the admin."""

    LIVENESS_MODES = [
        ("http", "Built-in HTTP check (looks for the expiry phrases below)"),
        ("node", "career-ops checker (Playwright, handles JavaScript sites)"),
    ]
    SIGNUP_MODES = [
        ("closed", "Closed: only users you create in the admin (and Google accounts on the allowed list)"),
        ("open", "Open: anyone can register with a verified email, or sign in with Google"),
    ]

    site_title = models.CharField(max_length=80, default="StillOpen")
    signup_mode = models.CharField(max_length=10, choices=SIGNUP_MODES, default="closed")
    score_scale = models.FloatField(
        default=5.0,
        validators=[MinValueValidator(1.0)],
        help_text="Top of the score range used by evaluations. Match % = score / this x 100.",
    )
    urgent_days = models.PositiveIntegerField(
        default=7, help_text="Deadlines within this many days are highlighted and sorted first."
    )
    apply_followup_days = models.PositiveIntegerField(
        default=7, validators=[MinValueValidator(1)], help_text="Default number of days before a follow-up reminder after someone applies.",
    )
    auto_close_expired = models.BooleanField(
        default=True,
        help_text="Show applications whose posting is confirmed expired under the closed tab (unless already applied).",
    )

    careerops_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Site admins only: folder of a career-ops project on this server (reads data/applications.md, reports/, output/).",
    )
    node_command = models.CharField(max_length=200, default="node", help_text="Command used to run career-ops scripts.")

    liveness_mode = models.CharField(max_length=10, choices=LIVENESS_MODES, default="http")
    liveness_timeout = models.PositiveIntegerField(default=60, help_text="Seconds allowed per posting check.")

    paperless_enabled = models.BooleanField(default=False, help_text="Site admins only. One Paperless for the whole server.")
    paperless_url = models.CharField(
        max_length=300, blank=True, help_text="Base URL of Paperless-ngx, e.g. http://127.0.0.1:8010"
    )
    paperless_token = models.CharField(
        max_length=200,
        blank=True,
        help_text="API token. The PAPERLESS_TOKEN environment variable takes precedence if set.",
    )
    paperless_verify_tls = models.BooleanField(default=True)
    paperless_auto_upload = models.BooleanField(
        default=False, help_text="Upload documents to Paperless automatically when they are imported."
    )

    google_login_enabled = models.BooleanField(
        default=False,
        help_text="Allow signing in with Google. Also needs a Google app under Social applications.",
    )
    google_allowed_emails = models.TextField(
        blank=True,
        help_text=(
            "Who may sign in with Google while sign-up is Closed, one per line: a full address (you@gmail.com) or a whole "
            "domain (@company.com). With sign-up Open, any Google account with a verified email may register. "
            "An existing user with the same verified email can always sign in."
        ),
    )

    profile_preferences = models.TextField(
        blank=True, help_text="Legacy single-user field. Per-person preferences now live on each user's profile."
    )

    landing_enabled = models.BooleanField(
        default=True, help_text="Show the public landing page at the site root. Off sends visitors straight to sign-in."
    )
    landing_headline = models.CharField(max_length=140, default="Stop applying to jobs that are already closed.")
    landing_subheadline = models.CharField(
        max_length=300,
        default=(
            "StillOpen tracks every role you are chasing, scores how well it fits you, "
            "and checks whether each posting is still open."
        ),
    )
    landing_github_url = models.URLField(blank=True, help_text="Optional. Adds a GitHub link to the landing page.")

    privacy_text = models.TextField(default=DEFAULT_PRIVACY, help_text="Shown at /privacy/. Replace with your own policy.")
    terms_text = models.TextField(default=DEFAULT_TERMS, help_text="Shown at /terms/. Replace with your own terms.")

    class Meta:
        verbose_name = "Site configuration"
        verbose_name_plural = "Site configuration"

    def __str__(self):
        return "Site configuration"

    def save(self, *args, **kwargs):
        if getattr(self, "_readonly", False):
            raise RuntimeError("A per-user configuration view cannot be saved; edit the user's profile instead.")
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # singleton
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def for_user(cls, user):
        """Site settings overlaid with this person's own AI, RAG and CV settings. Read-only; never saved."""
        config = cls.load()
        profile = UserProfile.for_user(user)
        for name in PER_USER_FIELDS:
            setattr(config, name, getattr(profile, name))
        config.profile_preferences = profile.preferences_text()
        config._readonly = True
        config.restricted = not user.is_staff
        if config.restricted:
            config.careerops_path = ""
            config.liveness_mode = "http"
            if config.ai_provider in ("claude_cli", "agent_sdk"):
                config.ai_provider = "none"
        return config

    def google_email_allowed(self, email: str) -> bool:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            return False
        domain = "@" + email.rsplit("@", 1)[1]
        for line in self.google_allowed_emails.splitlines():
            rule = line.strip().lower()
            if rule and rule in (email, domain):
                return True
        return False

    @property
    def signup_open(self) -> bool:
        return self.signup_mode == "open"

    @property
    def effective_paperless_token(self):
        return os.environ.get("PAPERLESS_TOKEN", "").strip() or self.paperless_token.strip()

    @property
    def effective_paperless_url(self):
        return (os.environ.get("PAPERLESS_URL", "").strip() or self.paperless_url.strip()).rstrip("/")


class UserProfile(PersonalSettings):
    """Everything personal to one user: who they are, what they want, their CV and their AI settings."""

    EMPLOYMENT = [
        ("full_time", "Full-time"), ("part_time", "Part-time"), ("contract", "Contract"),
        ("freelance", "Freelance"), ("internship", "Internship"),
    ]
    SENIORITY = [
        ("junior", "Junior"), ("mid", "Mid-level"), ("senior", "Senior"),
        ("lead", "Lead or staff"), ("principal", "Principal or architect"), ("manager", "Manager"),
    ]
    REMOTE = [
        ("any", "No preference"),
        ("remote", "Remote only"),
        ("hybrid", "Hybrid"),
        ("onsite", "On-site"),
        ("relocate", "Open to relocating"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    target_roles = models.TextField(blank=True, help_text="The roles you want, one per line (e.g. Senior Backend Engineer).")
    # Legacy single-choice fields. Replaced by SearchArea rows; kept so old data can be migrated.
    locations = models.TextField(blank=True, editable=False)
    remote_preference = models.CharField(max_length=10, choices=REMOTE, default="any", editable=False)
    home_country = models.CharField(max_length=2, blank=True, help_text="The country you live in. Remote jobs limited to one country only fit you if it is this one.")
    employment_types = models.JSONField(default=list, blank=True)
    seniority_levels = models.JSONField(default=list, blank=True)
    industries = models.TextField(blank=True, help_text="Industries you want, one per line (or leave blank for any).")
    languages = models.TextField(blank=True, help_text="Languages you can work in, one per line.")
    notice_period = models.CharField(max_length=60, blank=True, help_text="e.g. 30 days, or available now.")
    salary_floor = models.CharField(max_length=60, blank=True, help_text="Your minimum, with currency and period (e.g. 100,000 BDT/month).")
    deal_breakers = models.TextField(blank=True, help_text="Things you will not accept, one per line.")
    about = models.TextField(blank=True, help_text="Anything else the AI should know when judging fit.")
    self_registered = models.BooleanField(
        default=False, editable=False,
        help_text="Created through the public sign-up form. These accounts must confirm their email before they can sign in.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user}"

    @classmethod
    def for_user(cls, user):
        profile, _ = cls.objects.get_or_create(user=user)
        return profile

    def preferences_text(self) -> str:
        """Everything the person wants, as text for the AI. Search areas are described one per line."""

        def lines(text):
            return "; ".join(l.strip() for l in text.splitlines() if l.strip())

        parts = []
        if self.target_roles.strip():
            parts.append("Target roles: " + lines(self.target_roles))
        if self.home_country:
            from .services import geo

            parts.append("Lives in: " + geo.country_name(self.home_country))
        areas = list(self.user.search_areas.all()) if self.pk else []
        if areas:
            parts.append("Where I can work:\n" + "\n".join(f"- {a.describe()}" for a in areas))
        else:  # profiles saved before search areas existed
            if self.locations.strip():
                parts.append("Locations: " + lines(self.locations))
            if self.remote_preference != "any":
                parts.append("Work arrangement: " + self.get_remote_preference_display())
        labels = dict(self.EMPLOYMENT)
        if self.employment_types:
            parts.append("Employment types: " + ", ".join(labels.get(k, k) for k in self.employment_types))
        labels = dict(self.SENIORITY)
        if self.seniority_levels:
            parts.append("Seniority: " + ", ".join(labels.get(k, k) for k in self.seniority_levels))
        if self.industries.strip():
            parts.append("Industries: " + lines(self.industries))
        if self.languages.strip():
            parts.append("Languages: " + lines(self.languages))
        if self.notice_period.strip():
            parts.append("Notice period: " + self.notice_period.strip())
        if self.salary_floor.strip():
            parts.append("Salary floor: " + self.salary_floor.strip())
        if self.deal_breakers.strip():
            parts.append("Deal-breakers: " + lines(self.deal_breakers))
        if self.about.strip():
            parts.append(self.about.strip())
        return "\n".join(parts)

    @property
    def is_complete(self) -> bool:
        return bool(self.profile_cv.strip() and self.target_roles.strip())


class SearchArea(models.Model):
    """One place a person is willing to work, and on what terms. A job is checked against these rows."""

    CURRENCIES_HELP = "3-letter code, e.g. USD, BDT, MYR, AED."
    PERIODS = [("month", "per month"), ("year", "per year"), ("hour", "per hour")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_areas")
    order = models.PositiveIntegerField(default=0)
    place = models.CharField(
        max_length=80,
        help_text="A country (Malaysia), a region (Gulf, Europe, Southeast Asia), or Anywhere for remote work worldwide.",
    )
    city = models.CharField(max_length=80, blank=True, help_text="Optional. Only matters for on-site and hybrid work.")
    allow_remote = models.BooleanField(default=False)
    allow_hybrid = models.BooleanField(default=False)
    allow_onsite = models.BooleanField(default=False)
    needs_visa_sponsorship = models.BooleanField(default=False, help_text="Only if the employer sponsors your visa.")
    needs_relocation_support = models.BooleanField(default=False, help_text="Only if the employer helps with relocation.")
    min_salary = models.PositiveIntegerField(null=True, blank=True)
    salary_currency = models.CharField(max_length=3, blank=True, help_text=CURRENCIES_HELP)
    salary_period = models.CharField(max_length=5, choices=PERIODS, default="month")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.describe()

    @property
    def arrangements(self) -> list[str]:
        return [name for name, on in (("remote", self.allow_remote), ("hybrid", self.allow_hybrid), ("on-site", self.allow_onsite)) if on]

    def describe(self) -> str:
        where = f"{self.city}, {self.place}" if self.city else self.place
        bits = ["/".join(self.arrangements) or "no arrangement chosen"]
        if self.needs_visa_sponsorship:
            bits.append("only with visa sponsorship")
        if self.needs_relocation_support:
            bits.append("only with relocation support")
        if self.min_salary:
            bits.append(f"at least {self.min_salary:,} {self.salary_currency.upper()} {self.get_salary_period_display()}".replace("  ", " "))
        return f"{where}: " + ", ".join(bits)


class Bucket(models.Model):
    """A dashboard tab. Statuses point at one."""

    key = models.SlugField(unique=True)
    label = models.CharField(max_length=60)
    order = models.PositiveIntegerField(default=0)
    is_closed = models.BooleanField(
        default=False, help_text="Expired postings move into the bucket marked as closed."
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["order", "label"]

    def __str__(self):
        return self.label


class Status(models.Model):
    name = models.CharField(max_length=40, unique=True)
    bucket = models.ForeignKey(Bucket, on_delete=models.PROTECT, related_name="statuses")
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=9, default="#8b93a7", help_text="Hex colour, e.g. #3ecf8e")
    counts_as_applied = models.BooleanField(
        default=False, help_text="Setting this status stamps the applied date and counts the CV as submitted."
    )
    is_terminal = models.BooleanField(
        default=False, help_text="Terminal applications are skipped by the open/closed check."
    )

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "statuses"

    def __str__(self):
        return self.name


class ScoreBand(models.Model):
    """Colour and label for a match percentage, e.g. Strong >= 80."""

    label = models.CharField(max_length=40)
    min_percent = models.PositiveIntegerField(help_text="Lowest match % that falls in this band.")
    color = models.CharField(max_length=9, default="#3ecf8e")

    class Meta:
        ordering = ["-min_percent"]

    def __str__(self):
        return f"{self.label} (>= {self.min_percent}%)"


class Source(models.Model):
    """Job site, matched against the posting URL host."""

    name = models.CharField(max_length=60)
    host_contains = models.CharField(max_length=100, help_text="Text that appears in the URL host, e.g. linkedin.com")

    def __str__(self):
        return self.name


class ExpiredPhrase(models.Model):
    """Text that means a posting is closed (used by the built-in HTTP check)."""

    phrase = models.CharField(max_length=200, unique=True)
    note = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return self.phrase


class DocumentKind(models.Model):
    name = models.CharField(max_length=60, unique=True)
    keywords = models.CharField(
        max_length=200,
        blank=True,
        help_text="Comma-separated words in a file name that mark this kind, e.g. cover,letter",
    )
    paperless_tag = models.CharField(max_length=60, blank=True, help_text="Tag applied in Paperless-ngx.")
    paperless_document_type = models.CharField(max_length=60, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def matches(self, filename: str) -> bool:
        name = filename.lower()
        return any(k.strip().lower() in name for k in self.keywords.split(",") if k.strip())


class Application(models.Model):
    RISKS = [("", "—"), ("Low", "Low"), ("Medium", "Medium"), ("High", "High")]
    CHANNELS = [
        ("", "Not recorded"),
        ("site", "Company site or job board"),
        ("linkedin", "LinkedIn"),
        ("email", "Email"),
        ("referral", "Referral"),
        ("recruiter", "Recruiter or agency"),
        ("other", "Other"),
    ]
    LIVE = [
        ("unknown", "Not checked"),
        ("active", "Open"),
        ("expired", "Closed"),
        ("uncertain", "Unclear"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="applications",
        help_text="Whose job search this belongs to. Everyone sees only their own.",
    )
    careerops_num = models.PositiveIntegerField(null=True, blank=True, help_text="Row # in the career-ops tracker.")
    company = models.CharField(max_length=160)
    role = models.CharField(max_length=200)
    url = models.URLField(max_length=600, blank=True)
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.ForeignKey(Status, on_delete=models.PROTECT, related_name="applications")

    score = models.FloatField(null=True, blank=True, help_text="Evaluation score (0 to the configured scale).")
    decision = models.CharField(max_length=120, blank=True, help_text="Verdict from the evaluation, e.g. Consider.")
    legitimacy = models.CharField(max_length=60, blank=True)
    risk = models.CharField(max_length=10, choices=RISKS, blank=True)
    summary = models.TextField(blank=True, help_text="Short summary shown on the card.")
    next_action = models.TextField(blank=True)
    advertised_pay = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    found_date = models.DateField(default=date.today)
    applied_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    report_path = models.CharField(max_length=500, blank=True, help_text="Path to the career-ops report (relative to the career-ops folder).")
    description = models.TextField(blank=True, help_text="Job description text. Paste it, or leave blank to fetch it from the URL.")
    ARRANGEMENTS = [("", "Unknown"), ("remote", "Remote"), ("hybrid", "Hybrid"), ("onsite", "On-site")]
    YES_NO = [("", "Not stated"), ("yes", "Yes"), ("no", "No")]
    SOURCES_OF_DETAILS = [("", ""), ("detected", "Detected from the posting"), ("manual", "Set by you")]
    location_text = models.CharField(max_length=160, blank=True, help_text="As the posting says it, e.g. Kuala Lumpur, Malaysia or Remote.")
    country = models.CharField(max_length=2, blank=True, help_text="Two-letter country code where you must be based, if known (MY, BD, AE). Blank = not stated.")
    arrangement = models.CharField(max_length=10, choices=ARRANGEMENTS, blank=True)
    sponsorship = models.CharField(max_length=3, choices=YES_NO, blank=True, help_text="Does the employer offer visa sponsorship?")
    relocation = models.CharField(max_length=3, choices=YES_NO, blank=True, help_text="Does the employer offer relocation support?")
    employment_type = models.CharField(max_length=12, choices=[("", "Unknown")] + UserProfile.EMPLOYMENT, blank=True)
    seniority = models.CharField(max_length=10, choices=[("", "Unknown")] + UserProfile.SENIORITY, blank=True)
    details_source = models.CharField(max_length=10, choices=SOURCES_OF_DETAILS, blank=True)
    applied_cv = models.ForeignKey(
        "CVVersion", null=True, blank=True, on_delete=models.RESTRICT, related_name="sent_for",
        help_text="The exact CV version that was sent. It cannot be deleted while it is recorded here.",
    )
    applied_channel = models.CharField(max_length=10, choices=CHANNELS, blank=True)
    applied_note = models.CharField(max_length=300, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    jd_at_apply = models.TextField(blank=True, help_text="The job description as it was when the application was sent (postings disappear).")
    ai_evaluated_at = models.DateTimeField(null=True, blank=True)
    ai_method = models.CharField(max_length=40, blank=True)

    live_state = models.CharField(max_length=10, choices=LIVE, default="unknown")
    live_detail = models.CharField(max_length=300, blank=True)
    live_checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-careerops_num", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "careerops_num"], name="uniq_owner_careerops_num"),
        ]

    def __str__(self):
        return f"{self.company} - {self.role}"

    def save(self, *args, **kwargs):
        if not self.source_id and self.url:
            host = (urlparse(self.url).hostname or "").lower()
            for src in Source.objects.all():
                if src.host_contains.lower() in host:
                    self.source = src
                    break
        super().save(*args, **kwargs)

    # --- derived values -----------------------------------------------------

    def match_percent(self, scale: float = 5.0):
        if self.score is None or scale <= 0:
            return None
        return max(0, min(100, round(self.score / scale * 100)))

    def days_left(self, today: date | None = None):
        if not self.deadline:
            return None
        return (self.deadline - (today or timezone.localdate())).days

    def effective_bucket(self, config: "SiteConfig"):
        bucket = self.status.bucket
        if config.auto_close_expired and self.live_state == "expired" and not self.status.counts_as_applied:
            closed = Bucket.objects.filter(is_closed=True).first()
            if closed:
                return closed
        return bucket


class Insight(models.Model):
    KINDS = [("strength", "Strength"), ("gap", "Gap or risk")]

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="insights")
    kind = models.CharField(max_length=10, choices=KINDS)
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["kind", "order", "id"]

    def __str__(self):
        return f"{self.kind}: {self.text[:60]}"


class CVVersion(models.Model):
    """One immutable snapshot of a CV: a master version (the person's own CV over time) or one tailored for a job.

    Content never changes after creation; editing makes a new version whose parent is the old one. A tailored
    version is only exported once it is approved, and it is flagged when it states things the person's own
    material does not support."""

    KINDS = [("master", "Master CV"), ("tailored", "Tailored for a job")]
    SOURCES = [
        ("manual", "Written or edited by hand"),
        ("ai", "AI"),
        ("keywords", "Keyword tailoring (no AI)"),
        ("restored", "Restored from an earlier version"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cv_versions")
    application = models.ForeignKey(Application, null=True, blank=True, on_delete=models.CASCADE, related_name="cv_versions")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    kind = models.CharField(max_length=10, choices=KINDS, default="master")
    source = models.CharField(max_length=10, choices=SOURCES, default="manual")
    label = models.CharField(max_length=140, blank=True)
    content = models.TextField(help_text="The CV in Markdown.")
    provider = models.CharField(max_length=40, blank=True, help_text="Which AI provider wrote it, if any.")
    job_snapshot = models.TextField(blank=True, help_text="The job description as it was when this was made (postings disappear).")
    check_report = models.JSONField(default=list, blank=True, help_text="Claims the fact check could not find in the person's own material.")
    approved = models.BooleanField(default=False, help_text="The person has reviewed any flagged items and accepts this version.")
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "CV version"

    def __str__(self):
        return self.label or f"{self.get_kind_display()} #{self.pk}"

    def save(self, *args, **kwargs):
        if self.pk:
            old = CVVersion.objects.filter(pk=self.pk).values("content", "kind", "owner_id").first()
            if old and (old["content"] != self.content or old["kind"] != self.kind or old["owner_id"] != self.owner_id):
                raise ValueError("A CV version cannot be changed. Create a new version instead.")
        super().save(*args, **kwargs)

    @property
    def flagged(self) -> bool:
        return bool(self.check_report)

    @property
    def exportable(self) -> bool:
        """Master versions are the person's own words; tailored ones need approval when anything was flagged."""
        return self.kind == "master" or self.approved or not self.check_report


class Document(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    kind = models.ForeignKey(DocumentKind, on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="documents/%Y/%m/", blank=True)
    source_path = models.CharField(
        max_length=600,
        blank=True,
        help_text="Existing file on disk (used when no upload). Must be inside the career-ops folder or the media folder.",
    )
    paperless_id = models.PositiveIntegerField(null=True, blank=True)
    paperless_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind__order", "-created_at"]

    def __str__(self):
        return self.title


class Event(models.Model):
    KINDS = [
        ("note", "Note"),
        ("status", "Status change"),
        ("applied", "Submitted"),
        ("interview", "Interview"),
        ("followup", "Follow-up"),
        ("other", "Other"),
    ]

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    happened_at = models.DateTimeField(default=timezone.now)
    kind = models.CharField(max_length=12, choices=KINDS, default="note")
    text = models.CharField(max_length=500)

    class Meta:
        ordering = ["-happened_at"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.text[:60]}"


class KnowledgeSource(models.Model):
    """A document about the candidate that the AI may draw on: CV, project write-ups, notes, cover letters."""

    KINDS = [
        ("cv", "CV / resume"),
        ("experience", "Work experience details"),
        ("project", "Project"),
        ("education", "Education / certificates"),
        ("skills", "Skills"),
        ("writing", "Writing sample / cover letter"),
        ("other", "Other"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="knowledge_sources"
    )
    key = models.CharField(
        max_length=160, null=True, blank=True, editable=False,
        help_text="Set for sources kept in sync automatically (pasted CV, career-ops files).",
    )
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=KINDS, default="other")
    text = models.TextField(blank=True, help_text="The content. Paste it, or upload a .txt/.md/.pdf file below and it is read into here.")
    file = models.FileField(upload_to="knowledge/", blank=True, help_text="Optional .txt, .md or .pdf (max 2 MB).")
    enabled = models.BooleanField(default=True, help_text="Untick to keep it but stop the AI from seeing it.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "title"]
        constraints = [models.UniqueConstraint(fields=["owner", "key"], name="uniq_owner_knowledge_key")]

    def __str__(self):
        return self.title


class KnowledgeChunk(models.Model):
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="chunks")
    position = models.PositiveIntegerField(default=0)
    text = models.TextField()
    embedding = models.JSONField(null=True, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["source_id", "position"]


class LivenessRun(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="liveness_runs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    running = models.BooleanField(default=True)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class JobSource(models.Model):
    """A company's job board to search, via a zero-token public ATS API (no AI call to discover a posting).

    Admin-managed: this fetches from a specific external host, so it is restricted the same way the career-ops
    folder and Paperless URL are (server-side features the admin controls, not something an ordinary visitor
    can point at an arbitrary address)."""

    CONNECTORS = [
        ("greenhouse", "Greenhouse"),
        ("lever", "Lever"),
        ("ashby", "Ashby"),
    ]

    name = models.CharField(max_length=120, help_text="Company name, shown in the scan log and as the job's source.")
    connector = models.CharField(max_length=12, choices=CONNECTORS)
    board_token = models.CharField(
        max_length=80,
        help_text="The board token from the ATS's own job-board URL, e.g. 'resend' for jobs.ashbyhq.com/resend, "
        "or 'acme' for boards.greenhouse.io/acme. Letters, digits, dot, dash and underscore only.",
        validators=[RegexValidator(r"^[A-Za-z0-9._-]+$", "Only letters, digits, dot, dash and underscore.")],
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["connector", "board_token"], name="uniq_connector_token")]

    def __str__(self):
        return f"{self.name} ({self.get_connector_display()})"


class ScanRun(models.Model):
    """One person's job-search run over every enabled JobSource. Mirrors LivenessRun's shape and lifecycle."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="scan_runs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    running = models.BooleanField(default=True)
    total = models.PositiveIntegerField(default=0, help_text="Number of enabled sources to check.")
    done = models.PositiveIntegerField(default=0, help_text="Sources checked so far.")
    found = models.PositiveIntegerField(default=0, help_text="Postings seen across all sources.")
    added = models.PositiveIntegerField(default=0, help_text="New applications created.")
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class ScanLogEntry(models.Model):
    """Per-source result of one ScanRun: exactly what was searched and what it found, for the scan log panel."""

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name="entries")
    source_name = models.CharField(max_length=120)
    connector = models.CharField(max_length=12, choices=JobSource.CONNECTORS)
    found = models.PositiveIntegerField(default=0, help_text="Postings returned by this source.")
    matched = models.PositiveIntegerField(default=0, help_text="Postings whose title matched one of your target roles.")
    added = models.PositiveIntegerField(default=0, help_text="New applications created from this source.")
    duplicates = models.PositiveIntegerField(default=0, help_text="Matched postings already in your tracker.")
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
