import os
import re
from datetime import date
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .services.tz import validate_timezone

from . import copy, crypto, legal

# Settings that belong to one person. SiteConfig holds legacy values (used to seed the first user);
# every request works with SiteConfig.for_user(user), which overlays the person's own profile.
PER_USER_FIELDS = [
    "ai_provider", "ai_model", "ai_base_url", "ai_custom_headers", "ai_custom_body", "ai_custom_response_path",
    "ai_claude_command", "ai_timeout", "ai_max_input_chars", "ai_key_encrypted", "profile_cv",
    "rag_enabled", "rag_mode", "rag_top_k", "rag_chunk_chars", "rag_always_chars",
    "rag_embedding_base_url", "rag_embedding_model", "rag_embedding_key_encrypted",
]


def validate_https_url(value):
    """A public address of this site: https only (a blank value is allowed by the field itself)."""
    from django.core.exceptions import ValidationError

    if not str(value).lower().startswith("https://"):
        raise ValidationError("Use an address that starts with https://, for example https://jobs.example.com.")


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


DEFAULT_PRIVACY = legal.PRIVACY
DEFAULT_TERMS = legal.TERMS


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
    # Sign-up and sign-in abuse protection (no CAPTCHA: nothing third-party is ever loaded). See services/abuse.py.
    signup_protection = models.BooleanField(
        default=True,
        help_text="Quietly turn away bots at sign-up: a hidden trap box people never see and a minimum time to fill the form. "
        "A bot gets the same \"check your email\" page as anyone, without an account being made.",
    )
    signup_min_seconds = models.PositiveSmallIntegerField(
        default=2, validators=[MaxValueValidator(60)],
        help_text="A sign-up form sent faster than this many seconds after it was opened is treated as a bot. 0 turns the timing check off.",
    )
    signup_form_max_hours = models.PositiveSmallIntegerField(
        default=24, validators=[MinValueValidator(1), MaxValueValidator(168)],
        help_text="A sign-up page left open longer than this many hours has to be reloaded (stops a saved page being replayed another day).",
    )
    signup_per_hour_per_ip = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1)], help_text="New accounts one internet address may create per hour.",
    )
    login_failures_per_ip = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(1)], help_text="Wrong passwords one internet address may try in 10 minutes before being asked to wait.",
    )
    login_failures_per_account = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1)], help_text="Wrong passwords tried against one account (from anywhere) in 5 minutes before being asked to wait.",
    )
    password_reset_per_hour = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1)], help_text="Password-reset emails one internet address, or one email address, may ask for per hour.",
    )
    email_resend_seconds = models.PositiveSmallIntegerField(
        default=180, validators=[MaxValueValidator(3600)], help_text="Minimum wait before another confirmation email goes to the same address. 0 means no wait.",
    )
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
    followup_emails_enabled = models.BooleanField(
        default=False,
        help_text="Send a daily digest email when someone has a follow-up due. Needs email set up (Site configuration > Email) -- "
        "without it, emails only print to the server console. Run `manage.py send_followup_emails` on a schedule (e.g. daily cron).",
    )

    update_check_enabled = models.BooleanField(
        default=False, verbose_name="Check GitHub for a newer release",
        help_text="Off by default: this install never contacts anyone on its own. When ticked, at most once every six hours (and only when an admin "
        "opens the dashboard) the server makes one plain GET request to https://api.github.com/repos/Druvo/stillopen/releases/latest, the public "
        "releases list, and compares the newest release number with the one running (the VERSION file). Nothing about you, your people or this "
        "install is sent. If it works, admins see a small notice with a link to the release notes; if it fails, nothing happens.",
    )

    weekly_emails_enabled = models.BooleanField(
        default=False,
        help_text="Allow the weekly 'what to do this week' email to people who opted in (Profile > Emails). Needs email set up (Site configuration > Email). "
        "Run `manage.py send_weekly_summary` on a schedule (e.g. one cron line each morning); nobody gets it twice in six days.",
    )
    public_base_url = models.URLField(
        blank=True, max_length=200, validators=[validate_https_url],
        help_text="The address people open this site at, for example https://jobs.example.com. Emails link back to it. "
        "Blank: the Sites domain is used when it has been set, otherwise emails carry no link.",
    )

    prep_enabled = models.BooleanField(
        default=True,
        help_text="Let people turn a job's skill gaps into a short prep plan (needs their own AI key). Off hides the feature.",
    )
    prep_default_weeks = models.PositiveSmallIntegerField(default=4, help_text="Length of a new prep plan unless the person picks another.")
    prep_default_hours = models.PositiveSmallIntegerField(default=6, help_text="Study hours a week a new prep plan assumes.")
    prep_daily_questions = models.PositiveSmallIntegerField(default=3, help_text="Questions in each day's practice (1 to 10).")
    prep_max_weeks = models.PositiveSmallIntegerField(default=8, help_text="The longest plan a person may ask for.")
    prep_max_active_plans = models.PositiveSmallIntegerField(default=3, help_text="Plans one person can have in progress at once.")
    prep_questions_per_lesson = models.PositiveSmallIntegerField(default=3, help_text="Quiz questions written for each lesson (1 to 6).")
    prep_runs_per_day = models.PositiveSmallIntegerField(default=3, help_text="How many plans one person may ask for each day (each uses their own AI key).")
    prep_check_sources = models.BooleanField(default=True, help_text="Open every cited link once to see that it answers. Links that do not are flagged, not removed.")

    mcp_remote_enabled = models.BooleanField(
        default=True,
        help_text="Let people connect an AI assistant (Claude Code or any MCP client) to their own account over the web, with a "
        "personal token made under Profile > Connect an AI assistant. Off hides the page and answers 404 at /mcp/.",
    )

    auto_scan_hours = models.PositiveIntegerField(
        default=12,
        help_text="Search for new jobs on a person's behalf when they open the dashboard and their last search is older than this many hours. "
        "0 turns automatic searching off (people can still press Search jobs). No cron needed, no AI used.",
    )
    scan_emails_enabled = models.BooleanField(
        default=False,
        help_text="Allow the scheduled job search to email people who opted in (Profile > Job alerts). Needs email set up (Site configuration > Email) -- "
        "without it, emails only print to the server console. Run `manage.py scheduled_scan` on a schedule (e.g. daily cron).",
    )
    weekly_digest_site_enabled = models.BooleanField(
        default=False,
        help_text="Allow the weekly digest to email people who opted in (Profile > Job alerts). Needs email set up (Site configuration > Email) -- "
        "without it, emails only print to the server console. Run `manage.py send_weekly_digest` on a schedule (e.g. weekly cron).",
    )

    draft_ahead_site_enabled = models.BooleanField(
        default=False,
        help_text="Allow the scheduled job search to also prepare tailored CV drafts for the best new matches of people who opted in "
        "(Profile > Job alerts). Each draft uses that person's own AI settings and waits for their review; nothing is approved, downloaded "
        "or sent for them. Capped per run by STILLOPEN_DRAFT_AHEAD_MAX (default 3).",
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
    jooble_api_key = models.CharField(
        max_length=200, blank=True,
        help_text="Free key from jooble.org/api/about (Jooble approves it by email). Switches on the Jooble sources, which add "
        "Bangladesh, Malaysia and the Gulf. The JOOBLE_API_KEY environment variable takes precedence. Never shown again.",
    )
    adzuna_app_id = models.CharField(
        max_length=80, blank=True,
        help_text="Free app id from developer.adzuna.com (register, then copy the id and key from your dashboard). Switches on the Adzuna "
        "sources: 19 countries including the UK, US, India, Singapore, South Africa and Brazil. The ADZUNA_APP_ID environment variable takes precedence.",
    )
    adzuna_app_key_encrypted = models.CharField(max_length=500, blank=True)
    usajobs_api_key = models.CharField(
        max_length=200, blank=True,
        help_text="Free key from developer.usajobs.gov/apirequest (instant, no phone number). Switches on the USAJobs "
        "source: official, documented US federal job openings. The USAJOBS_API_KEY environment variable takes precedence.",
    )
    usajobs_email = models.EmailField(
        max_length=200, blank=True,
        help_text="The email address used to request the USAJobs key -- USAJobs requires it on every request, as the "
        "User-Agent. The USAJOBS_EMAIL environment variable takes precedence.",
    )
    languagetool_url = models.CharField(
        max_length=300, blank=True,
        help_text="Base URL of a LanguageTool server (self-hosted, e.g. with the erikvl87/languagetool Docker image, "
        "or https://api.languagetool.org for the public instance -- mind its rate limit and privacy if you use that "
        "one). Switches on a 'Check writing' button on CVs and cover letters. Off (nothing sent anywhere) when blank. "
        "The LANGUAGETOOL_URL environment variable takes precedence.",
    )
    libretranslate_url = models.CharField(
        max_length=300, blank=True,
        help_text="Base URL of a LibreTranslate server (self-hosted, e.g. the libretranslate/libretranslate Docker "
        "image, or a public instance that accepts your key). Switches on a 'Translate to English' button on a job's "
        "description. Off (nothing sent anywhere) when blank. The LIBRETRANSLATE_URL environment variable takes precedence.",
    )
    libretranslate_api_key = models.CharField(
        max_length=200, blank=True,
        help_text="Only needed if your LibreTranslate server requires one (most self-hosted instances don't). "
        "The LIBRETRANSLATE_API_KEY environment variable takes precedence.",
    )
    paperless_verify_tls = models.BooleanField(default=True)
    paperless_auto_upload = models.BooleanField(
        default=False, help_text="Upload documents to Paperless automatically when they are imported."
    )

    google_login_enabled = models.BooleanField(
        default=False,
        help_text="Allow signing in with Google. Also needs a Google app under Social applications.",
    )
    github_login_enabled = models.BooleanField(
        default=False, help_text="Allow signing in with GitHub. Also needs a GitHub OAuth app under Social applications.",
    )
    facebook_login_enabled = models.BooleanField(
        default=False, help_text="Allow signing in with Facebook. Also needs a Facebook app under Social applications.",
    )
    # Sign-in providers: the app's id and secret from Google, GitHub or Facebook. The environment (GOOGLE_CLIENT_ID...) takes precedence.
    google_client_id = models.CharField(max_length=200, blank=True)
    google_secret_encrypted = models.CharField(max_length=500, blank=True)
    github_client_id = models.CharField(max_length=200, blank=True)
    github_secret_encrypted = models.CharField(max_length=500, blank=True)
    facebook_client_id = models.CharField(max_length=200, blank=True)
    facebook_secret_encrypted = models.CharField(max_length=500, blank=True)
    # The opt-in "Connect my Google account" feature (send from Gmail, replies, Calendar): a SEPARATE OAuth client from the sign-in one above,
    # because it asks for more scopes and has its own redirect address. Blank = the feature is off. GOOGLE_OAUTH_CLIENT_ID / _SECRET take precedence.
    google_connect_client_id = models.CharField(max_length=200, blank=True)
    google_connect_secret_encrypted = models.CharField(max_length=500, blank=True)

    # Email sending (Brevo, Mailgun, any SMTP). The EMAIL_HOST environment variable takes precedence.
    email_host = models.CharField(max_length=200, blank=True, help_text="SMTP server, e.g. smtp-relay.brevo.com. Blank = email is not set up.")
    email_port = models.PositiveIntegerField(default=587)
    email_username = models.CharField(max_length=200, blank=True)
    email_password_encrypted = models.CharField(max_length=500, blank=True)
    email_use_tls = models.BooleanField(default=True, help_text="Leave on for port 587 (STARTTLS).")
    email_from = models.CharField(max_length=200, blank=True, help_text="The sender people see, e.g. StillOpen <jobs@yourdomain.com>. Use an address your provider has verified.")

    google_allowed_emails = models.TextField(
        blank=True,
        verbose_name="Allowed emails for social sign-in",
        help_text=(
            "Who may sign in with Google, GitHub or Facebook while sign-up is Closed, one per line: a full address (you@gmail.com) or "
            "a whole domain (@company.com). With sign-up Open, anyone with a verified email may register (a Facebook email is "
            "confirmed by the usual email link). An existing user with the same verified email can always sign in."
        ),
    )

    profile_preferences = models.TextField(
        blank=True, help_text="Legacy single-user field. Per-person preferences now live on each user's profile."
    )

    landing_enabled = models.BooleanField(
        default=True, help_text="Show the public landing page at the site root. Off sends visitors straight to sign-in."
    )
    landing_headline = models.CharField(max_length=140, default=copy.HEADLINE)
    landing_subheadline = models.CharField(max_length=300, default=copy.SUBHEADLINE)
    public_board_enabled = models.BooleanField(
        default=True,
        help_text="Show the public job board (/openings/) and its live numbers on the landing page. Only openings from sources marked "
        "'show publicly' appear, and only ones seen in the last few days.",
    )
    public_details_indexable = models.BooleanField(
        default=False,
        help_text="Let search engines index each opening's own page. Off by default: those pages are short excerpts of other people's "
        "postings, which search engines can treat as thin or copied content. The board, landing page and country views stay indexable.",
    )
    contact_email = models.EmailField(blank=True, help_text="Shown on the public pages for employers who want a listing removed, and for questions.")
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

    @property
    def email_password(self) -> str:
        return crypto.decrypt(self.email_password_encrypted)

    def set_email_password(self, plain: str) -> None:
        self.email_password_encrypted = crypto.encrypt(plain.strip())

    def social_secret(self, provider: str) -> str:
        return crypto.decrypt(getattr(self, f"{provider}_secret_encrypted"))

    def set_social_secret(self, provider: str, plain: str) -> None:
        setattr(self, f"{provider}_secret_encrypted", crypto.encrypt(plain.strip()))

    def set_google_connect_secret(self, plain: str) -> None:
        self.google_connect_secret_encrypted = crypto.encrypt(plain.strip())

    @property
    def effective_google_connect(self):
        """(client id, secret) for the Google connection (Gmail and Calendar), or None while either is blank: the feature is then off."""
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip() or self.google_connect_client_id.strip()
        secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip() or crypto.decrypt(self.google_connect_secret_encrypted)
        return (client_id, secret) if client_id and secret else None

    def social_enabled(self, provider: str) -> bool:
        return bool(getattr(self, f"{provider}_login_enabled", False))

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
    def effective_jooble_key(self):
        return os.environ.get("JOOBLE_API_KEY", "").strip() or self.jooble_api_key.strip()

    def set_adzuna_app_key(self, plain: str) -> None:
        self.adzuna_app_key_encrypted = crypto.encrypt(plain.strip())

    @property
    def effective_adzuna_id(self):
        return os.environ.get("ADZUNA_APP_ID", "").strip() or self.adzuna_app_id.strip()

    @property
    def effective_adzuna_key(self):
        return os.environ.get("ADZUNA_APP_KEY", "").strip() or crypto.decrypt(self.adzuna_app_key_encrypted)

    @property
    def effective_usajobs_key(self):
        return os.environ.get("USAJOBS_API_KEY", "").strip() or self.usajobs_api_key.strip()

    @property
    def effective_usajobs_email(self):
        return os.environ.get("USAJOBS_EMAIL", "").strip() or self.usajobs_email.strip()

    @property
    def effective_languagetool_url(self):
        return (os.environ.get("LANGUAGETOOL_URL", "").strip() or self.languagetool_url.strip()).rstrip("/")

    @property
    def effective_libretranslate_url(self):
        return (os.environ.get("LIBRETRANSLATE_URL", "").strip() or self.libretranslate_url.strip()).rstrip("/")

    @property
    def effective_libretranslate_api_key(self):
        return os.environ.get("LIBRETRANSLATE_API_KEY", "").strip() or self.libretranslate_api_key.strip()

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
    timezone = models.CharField(
        max_length=64, blank=True, validators=[validate_timezone],
        help_text="Your time zone (for example Asia/Dhaka), so \"today\", streaks, follow-ups and deadlines turn over at your midnight. Blank uses the site's time zone.",
    )
    employment_types = models.JSONField(default=list, blank=True)
    seniority_levels = models.JSONField(default=list, blank=True)
    industries = models.TextField(blank=True, help_text="Industries you want, one per line (or leave blank for any).")
    languages = models.TextField(blank=True, help_text="Languages you can work in, one per line.")
    notice_period = models.CharField(max_length=60, blank=True, help_text="e.g. 30 days, or available now.")
    salary_floor = models.CharField(max_length=60, blank=True, help_text="Your minimum, with currency and period (e.g. 100,000 BDT/month).")
    deal_breakers = models.TextField(blank=True, help_text="Things you will not accept, one per line.")
    about = models.TextField(blank=True, help_text="Anything else the AI should know when judging fit.")
    scan_digest_enabled = models.BooleanField(
        default=False, verbose_name="Search for new jobs for me and email me what is found",
        help_text="Runs your saved search on a schedule and emails one short list of new matches. Off until you turn it on.",
    )
    email_followups = models.BooleanField(
        default=True, verbose_name="Email me when a follow-up is due",
        help_text="Only sent when the site owner has turned follow-up emails on, and only to a verified address.",
    )
    email_interviews = models.BooleanField(
        default=True, verbose_name="Email me before an interview",
        help_text="Only sent when the site owner has turned reminder emails on, and only to a verified address.",
    )
    email_weekly = models.BooleanField(
        default=False, verbose_name="Email me a weekly plan",
        help_text="One short email a week: what is due, what is coming up and the best new matches. Off until you turn it on.",
    )
    weekly_emailed_at = models.DateTimeField(null=True, blank=True, editable=False, help_text="When the last weekly email went out, so it is never sent twice in six days.")
    notify_muted = models.JSONField(
        default=list, blank=True, editable=False,
        help_text="Kinds of in-app notice this person switched off (see services/notifications.py). Empty means all are on.",
    )
    ui_preferences = models.JSONField(
        default=dict, blank=True, editable=False,
        help_text="How this person likes the app laid out (dashboard view, filters, sidebar, theme, text size). Saved so it follows them to every device; see services/preferences.py.",
    )
    draft_ahead_enabled = models.BooleanField(
        default=False, verbose_name="Also prepare tailored CV drafts for my best new matches",
        help_text="After a scheduled search, writes a draft CV for the top new matches using your own AI settings. Drafts wait on your "
        "dashboard for you to check; nothing is approved, downloaded or sent for you. Off until you turn it on.",
    )
    weekly_digest_enabled = models.BooleanField(
        default=False, verbose_name="Email me a weekly summary of how my search is going",
        help_text="Applications sent, interviews, offers and follow-ups from the last 7 days -- the same plain "
        "counts the Insights page shows, delivered once a week. Off until you turn it on. Run "
        "`manage.py send_weekly_digest` on a schedule (e.g. a weekly cron).",
    )
    weekly_digest_sent_through = models.DateField(
        null=True, blank=True, editable=False,
        help_text="The Monday of the last week a digest was already sent for -- stops a cron run twice a week sending two emails.",
    )
    onboarding_done = models.BooleanField(
        default=False, editable=False,
        help_text="The person has seen (or skipped) the short welcome questions after signing up.",
    )
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
        return not self.missing_fields

    @property
    def missing_fields(self) -> list[str]:
        """Which of the two things a real match needs are still blank, so the dashboard banner can say which."""
        missing = []
        if not self.target_roles.strip():
            missing.append("the roles you want")
        if not self.profile_cv.strip():
            missing.append("your CV")
        return missing


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
    posting = models.ForeignKey(
        "Posting", null=True, blank=True, on_delete=models.SET_NULL, related_name="applications",
        help_text="The scanned posting this came from, if it was found by Search jobs. Blank for manually added or imported roles.",
    )
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
    description_is_excerpt = models.BooleanField(
        default=False,
        help_text="The saved description is only the start of the posting (a job search keeps a short excerpt). "
        "The full text is fetched from the posting's link the first time a check or tailoring needs it.",
    )
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
    gmail_thread_id = models.CharField(max_length=64, blank=True, help_text="The Gmail conversation the person's own connected account sent this application in (or linked). Replies are read from it only.")
    gmail_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_emailed_for = models.DateField(
        null=True, blank=True,
        help_text="The follow_up_date a reminder email was last sent for. Lets the daily digest send once per due "
        "date instead of re-notifying every day it stays overdue; a snooze or a new follow-up date clears it.",
    )
    jd_at_apply = models.TextField(blank=True, help_text="The job description as it was when the application was sent (postings disappear).")
    ai_evaluated_at = models.DateTimeField(null=True, blank=True)
    ai_method = models.CharField(max_length=40, blank=True)
    ai_summary = models.JSONField(
        default=dict, blank=True, editable=False,
        help_text="The latest \"what this role really needs\" reading of the posting, with red flags (services/assist.py). Separate from the person's own summary.",
    )

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
    draft_ahead = models.BooleanField(default=False, editable=False, help_text="Prepared automatically after a scheduled search; shown as a draft waiting for review until approved or discarded.")
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


class CoverLetter(models.Model):
    """A cover letter for one job. Unlike a CV version it is a plain draft the person edits in place; every save
    re-runs the fact check and withdraws any earlier approval, so what is exported was always the text that was
    checked (or approved) last."""

    SOURCES = [("ai", "AI"), ("keywords", "Built from your CV (no AI)"), ("manual", "Written or edited by hand")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cover_letters")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="cover_letters")
    content = models.TextField(help_text="The letter, plain text.")
    source = models.CharField(max_length=10, choices=SOURCES, default="manual")
    provider = models.CharField(max_length=40, blank=True)
    check_report = models.JSONField(default=list, blank=True)
    approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Cover letter for {self.application.company} - {self.application.role}"

    @property
    def flagged(self) -> bool:
        return bool(self.check_report)

    @property
    def exportable(self) -> bool:
        return self.approved or not self.check_report


class Interview(models.Model):
    """One scheduled conversation for a job: phone screen, video call, on-site. Owner-only, like everything personal."""

    KINDS = [
        ("phone", "Phone screen"), ("video", "Video call"), ("technical", "Technical round"),
        ("onsite", "On-site"), ("final", "Final round"), ("other", "Other"),
    ]
    OUTCOMES = [
        ("pending", "Not yet"), ("done", "Happened, waiting to hear"), ("passed", "Going well, moving on"),
        ("rejected", "Not moving on"), ("cancelled", "Cancelled"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interviews")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="interviews")
    scheduled_at = models.DateTimeField()
    kind = models.CharField(max_length=10, choices=KINDS, default="video")
    where = models.CharField(max_length=300, blank=True, help_text="Address, or the video-call link.")
    notes = models.TextField(blank=True, max_length=4000, help_text="Who you will meet, what to prepare, questions to ask.")
    outcome = models.CharField(max_length=10, choices=OUTCOMES, default="pending")
    reminded_at = models.DateTimeField(null=True, blank=True, editable=False, help_text="When the reminder email went out, if one did.")
    google_event_id = models.CharField(max_length=128, blank=True, editable=False, help_text="The Google Calendar event this app created for it (only ever one of ours).")
    google_event_updated = models.CharField(max_length=40, blank=True, editable=False, help_text="Google's own 'updated' stamp of that event as of our last sync.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at", "id"]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.application.company} on {self.scheduled_at:%d %b %Y %H:%M}"


class Contact(models.Model):
    """A person you know at, or near, a company you are applying to. Never contacted by the app."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=120)
    company = models.CharField(max_length=160, blank=True)
    title = models.CharField(max_length=160, blank=True, verbose_name="Their role")
    email = models.EmailField(blank=True)
    link = models.URLField(blank=True, max_length=300, verbose_name="Profile link")
    notes = models.TextField(blank=True, max_length=2000)
    last_contacted = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class Referral(models.Model):
    """A contact who may put in a word for you on one job."""

    STATUSES = [
        ("thinking", "Thinking of asking"), ("asked", "Asked"), ("agreed", "Agreed to refer me"),
        ("submitted", "Referral submitted"), ("declined", "Declined or no answer"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="referrals")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="referrals")
    status = models.CharField(max_length=10, choices=STATUSES, default="thinking")
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class ApiToken(models.Model):
    """A personal access token for the web MCP endpoint (/mcp/): lets an AI assistant act for one person, and only that person.

    Only a SHA-256 hash is stored (the token is 256 random bits, so a plain hash is enough); the token itself is shown once.
    A read-only token can call only the tools that cannot change anything."""

    PREFIX = "so_"
    EXPIRY_CHOICES = [(30, "30 days"), (90, "90 days"), (365, "1 year"), (0, "Never")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=60, help_text="What it is for, e.g. Claude Code on my laptop.")
    token_hash = models.CharField(max_length=64, unique=True)
    hint = models.CharField(max_length=12, help_text="The first characters, so a person can tell tokens apart. Not enough to use it.")
    can_write = models.BooleanField(default=False, help_text="Off: the assistant can only read. On: it can also add jobs, notes and the like (never delete).")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.hint}...)"

    @staticmethod
    def digest(raw: str) -> str:
        import hashlib

        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, owner, name: str, can_write: bool = False, days: int = 90):
        """Make a token. Returns (record, raw token); the raw token cannot be recovered later."""
        import secrets
        from datetime import timedelta

        raw = cls.PREFIX + secrets.token_urlsafe(32)
        record = cls.objects.create(
            owner=owner, name=name.strip()[:60] or "Assistant", token_hash=cls.digest(raw), hint=raw[:8], can_write=can_write,
            expires_at=timezone.now() + timedelta(days=days) if days else None,
        )
        return record, raw

    @classmethod
    def lookup(cls, raw: str):
        """The usable token for `raw` (not revoked, not expired, owner active), or None."""
        if not raw or not raw.startswith(cls.PREFIX) or len(raw) > 200:
            return None
        record = cls.objects.select_related("owner").filter(token_hash=cls.digest(raw)).first()
        if record is None or not record.is_usable:
            return None
        return record

    @property
    def is_usable(self) -> bool:
        if self.revoked_at or not self.owner.is_active:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    @property
    def state(self) -> str:
        if self.revoked_at:
            return "Revoked"
        if self.expires_at and self.expires_at <= timezone.now():
            return "Expired"
        return "Active"


class CalendarFeed(models.Model):
    """The private link a calendar app subscribes to (/calendar/<token>.ics): one per person, read-only.

    Only a SHA-256 hash is used to find the row; the link itself is kept encrypted (tracker/crypto.py) so the person can copy it again
    from the Interviews screen. Making a new link replaces this row's token, so the old one stops working at once."""

    PREFIX = "cal_"

    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed")
    token_hash = models.CharField(max_length=64, unique=True)
    token_encrypted = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"calendar link for {self.owner}"

    @staticmethod
    def digest(raw: str) -> str:
        import hashlib

        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, owner):
        """Make (or replace) the person's link. Returns (record, raw token)."""
        import secrets

        from .crypto import encrypt

        raw = cls.PREFIX + secrets.token_urlsafe(32)
        record, _ = cls.objects.update_or_create(
            owner=owner, defaults={"token_hash": cls.digest(raw), "token_encrypted": encrypt(raw), "created_at": timezone.now(), "last_used_at": None},
        )
        return record, raw

    @classmethod
    def lookup(cls, raw: str):
        """The feed for `raw` when the token is genuine and its owner is active, else None."""
        import hmac

        if not raw or not raw.startswith(cls.PREFIX) or len(raw) > 100:
            return None
        digest = cls.digest(raw)
        record = cls.objects.select_related("owner").filter(token_hash=digest).first()
        if record is None or not hmac.compare_digest(record.token_hash, digest) or not record.owner.is_active:
            return None
        return record

    @property
    def token(self) -> str:
        from .crypto import decrypt

        return decrypt(self.token_encrypted)


class Offer(models.Model):
    """A job offer, kept in plain numbers so offers can be set side by side. Amounts are per year unless the base is monthly."""

    PERIODS = [("year", "per year"), ("month", "per month")]
    STATUSES = [("open", "Deciding"), ("accepted", "Accepted"), ("declined", "Declined")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="offers")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="offers")
    base = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Base pay")
    period = models.CharField(max_length=5, choices=PERIODS, default="year")
    currency = models.CharField(max_length=3, default="USD", help_text="Three letters, e.g. USD, BDT, MYR, AED.")
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="Yearly bonus")
    equity = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="Yearly value of shares or options")
    signing = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="One-off signing bonus")
    other_benefits = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="Other yearly benefits worth counting", help_text="Allowances, insurance, pension match: only what you would otherwise pay for.")
    deadline = models.DateField(null=True, blank=True, verbose_name="Reply by")
    status = models.CharField(max_length=10, choices=STATUSES, default="open")
    notes = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    @property
    def yearly_base(self):
        return self.base * 12 if self.period == "month" else self.base

    @property
    def yearly_total(self):
        """Pay you can count on each year, leaving out the one-off signing bonus."""
        return self.yearly_base + self.bonus + self.equity + self.other_benefits

    @property
    def first_year_total(self):
        return self.yearly_total + self.signing


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
    undo = models.JSONField(
        null=True, blank=True, default=None, editable=False,
        help_text="For a status change: what the job looked like before it (status, applied date, follow-up date), so the person can undo it for a few minutes. See services/board.py.",
    )

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


def validate_board_token(value: str) -> None:
    """A board token (letters, digits, dot, dash, underscore), or for a careers page its https address."""
    if value.startswith("https://") and len(value) <= 300:
        return
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value or ""):
        raise ValidationError("Only letters, digits, dot, dash and underscore (or, for a careers page, its https address).")


class JobSource(models.Model):
    """A job board to search, via a zero-token public API or feed (no AI call to discover a posting).

    Admin-managed: this fetches from a specific external host, so it is restricted the same way the career-ops
    folder and Paperless URL are (server-side features the admin controls, not something an ordinary visitor
    can point at an arbitrary address).

    Two shapes of source: Greenhouse/Lever/Ashby are single-company boards (`board_token` is that company's
    slug in the ATS's own URL, e.g. 'resend' for jobs.ashbyhq.com/resend, and `name` is that company). RemoteOK/
    We Work Remotely/Himalayas are aggregators spanning many employers (`board_token` is an optional filter --
    a RemoteOK tag, a We Work Remotely category slug, or 'all' for no filter on either -- and the actual
    employer comes back per-posting, read from `Posting.company`, not from `name`)."""

    CONNECTORS = [
        ("greenhouse", "Greenhouse"),
        ("lever", "Lever"),
        ("ashby", "Ashby"),
        ("smartrecruiters", "SmartRecruiters"),
        ("recruitee", "Recruitee"),
        ("careerpage", "Company careers page"),
        ("remoteok", "RemoteOK"),
        ("weworkremotely", "We Work Remotely"),
        ("himalayas", "Himalayas"),
        ("remotive", "Remotive"),
        ("arbeitnow", "Arbeitnow"),
        ("jobicy", "Jobicy"),
        ("workingnomads", "Working Nomads"),
        ("themuse", "The Muse"),
        ("jooble", "Jooble (needs a free key)"),
        ("adzuna", "Adzuna (needs a free key)"),
        ("jobtech", "JobTech Sweden"),
        ("getonbrd", "Get on Board (Latin America)"),
        ("bdjobs", "Bangladesh -- bdjobs.com (undocumented API, off by default -- see scan.py)"),
        ("bikroy", "Bangladesh -- bikroy.com Jobs (undocumented API, off by default -- see scan.py)"),
        ("usajobs", "USAJobs -- official US federal jobs (needs a free key)"),
        ("hnhiring", "Startups -- Hacker News 'Who is hiring?' (off by default)"),
    ]

    name = models.CharField(max_length=120, help_text="Shown in the scan log. The company name for a single-company connector; a label like 'RemoteOK' for an aggregator.")
    connector = models.CharField(max_length=20, choices=CONNECTORS)
    board_token = models.CharField(
        max_length=300,
        help_text="Single-company connector: the board token from the ATS's own URL, e.g. 'resend' for "
        "jobs.ashbyhq.com/resend, 'acme' for boards.greenhouse.io/acme, 'Equinox' for "
        "jobs.smartrecruiters.com/Equinox, or 'channable' for channable.recruitee.com. Aggregator connector: an "
        "optional filter -- a RemoteOK tag (e.g. 'dev'), a We Work Remotely category slug (e.g. "
        "'remote-full-stack-programming-jobs'), or 'all' for no filter (Himalayas ignores this and always "
        "fetches its newest postings, since its public API has no working keyword filter to request narrower "
        "than that). Jooble: a country code (bd, my, ae, sa, qa, kw, bh, om). bdjobs / bikroy / usajobs: any "
        "value, e.g. 'bd' -- all three are a sitewide search, not a per-company board, so the token carries no "
        "meaning. Letters, digits, dot, dash and underscore only.",
        validators=[validate_board_token],
    )
    enabled = models.BooleanField(default=True)
    show_publicly = models.BooleanField(
        default=False,
        help_text="Show this site-wide source's openings on the public job board (no sign-in needed), each with a credit link to the original. "
        "Only tick it where the source's own terms allow public display; Remotive's, for example, do not. Never applies to a person's own boards.",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="job_sources",
        help_text="Empty: a site-wide source the admin manages, searched for everyone. Set: one person's own board, "
        "searched only for them and invisible to everyone else.",
    )

    # What a person may add for themselves: single-company boards only. Aggregators stay admin-managed.
    OWN_CONNECTORS = ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "careerpage"]

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "connector", "board_token"], name="uniq_owner_connector_token"),
            models.UniqueConstraint(
                fields=["connector", "board_token"], condition=models.Q(owner__isnull=True), name="uniq_sitewide_connector_token",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_connector_display()})"

    @classmethod
    def for_user(cls, user, enabled: bool | None = None):
        """The sources a person's searches may use and see: the site-wide ones plus their own, never anyone else's."""
        qs = cls.objects.filter(models.Q(owner__isnull=True) | models.Q(owner=user))
        return qs if enabled is None else qs.filter(enabled=enabled)


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
    added_ids = models.JSONField(default=list, blank=True, help_text="Primary keys of the applications this run created.")
    note = models.TextField(blank=True, help_text="Plain information about the run (for example that only the best matches were added). Not an error.")
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class ScanLogEntry(models.Model):
    """Per-source result of one ScanRun: exactly what was searched and what it found, for the scan log panel."""

    run = models.ForeignKey(ScanRun, on_delete=models.CASCADE, related_name="entries")
    source_name = models.CharField(max_length=120)
    connector = models.CharField(max_length=20, choices=JobSource.CONNECTORS)
    found = models.PositiveIntegerField(default=0, help_text="Postings returned by this source.")
    matched = models.PositiveIntegerField(default=0, help_text="Postings whose title matched one of your target roles.")
    added = models.PositiveIntegerField(default=0, help_text="New applications created from this source.")
    duplicates = models.PositiveIntegerField(default=0, help_text="Matched postings already in your tracker.")
    outside = models.PositiveIntegerField(default=0, help_text="Matched postings left out because they are clearly outside your search areas.")
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Posting(models.Model):
    """One posting ever seen at a JobSource, recorded on every scan whether or not it matched anyone's roles.

    This is what repost/ghost-job detection reads: a company re-listing the same role under a new URL shows up
    as several Postings sharing one `title_key` at the same `source`. Shared across every user watching that
    source -- a repost pattern is a property of the posting, not of any one person's search.

    `company` matters because a source isn't always one employer: for a single-company connector (Greenhouse/
    Lever/Ashby) it's always `source.name`, but for an aggregator (RemoteOK, We Work Remotely, Himalayas) it
    varies per posting -- so `title_key` is derived from company+title together, or two different real
    employers' same-titled roles on one aggregator would wrongly look like one company reposting."""

    source = models.ForeignKey(JobSource, on_delete=models.CASCADE, related_name="postings")
    url = models.URLField(max_length=600)
    company = models.CharField(max_length=160, blank=True, help_text="The actual employer. Same as the source's name for a single-company connector; varies per posting on an aggregator.")
    title = models.CharField(max_length=300)
    title_key = models.CharField(max_length=300, db_index=True, help_text="Normalized company+title, used to group reposts of the same role.")
    location = models.CharField(max_length=160, blank=True)
    country = models.CharField(max_length=2, blank=True, db_index=True, help_text="Two-letter country when the location names exactly one.")
    remote = models.BooleanField(default=False, help_text="The location or title says remote or worldwide.")
    apply_address = models.CharField(max_length=300, blank=True, help_text="An email or link the posting itself publishes for applying (Hacker News posts do). Shown as a plain link; the app never sends anything to it.")
    excerpt = models.TextField(blank=True, help_text="The first few lines of the posting, for the public board. The full text stays at the employer.")
    sponsorship = models.CharField(max_length=3, blank=True, db_index=True, help_text="'yes' only when the posting says the employer sponsors visas; 'no' when it says it cannot; blank = not stated.")
    relocation = models.CharField(max_length=3, blank=True, help_text="'yes' when the posting offers relocation help, 'no' when it says none; blank = not stated.")
    employment_type = models.CharField(max_length=12, blank=True, choices=UserProfile.EMPLOYMENT, help_text="Kind of contract, when the posting says.")
    seniority = models.CharField(max_length=10, blank=True, help_text="Level read from the title (junior, senior, lead...), when it says.")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [models.UniqueConstraint(fields=["source", "url"], name="uniq_source_url")]


class PostingSighting(models.Model):
    """One calendar day on which a Posting was seen in a scan. Distinct-day count (not raw scan count) is what
    tells a same-day batch of concurrent openings apart from a role re-listed on separate days."""

    posting = models.ForeignKey(Posting, on_delete=models.CASCADE, related_name="sightings")
    seen_date = models.DateField()

    class Meta:
        ordering = ["seen_date"]
        constraints = [models.UniqueConstraint(fields=["posting", "seen_date"], name="uniq_posting_seen_date")]


class AIUsageEvent(models.Model):
    """One paid-provider AI call (never the free keyword fallback, which costs nothing and isn't logged here).

    Token counts come straight from the provider's own response where it reports them (Anthropic, any
    OpenAI-compatible endpoint); `cost_usd` is either the provider's own reported figure (Claude Code CLI,
    Claude Agent SDK) or a best-effort estimate from a small static per-model price table (services/ai.py) --
    never exact for every model, which is why the UI always labels it an estimate. A provider this can't
    measure at all (Custom HTTP, whose response shape is unknowable in general) simply logs no tokens/cost,
    not a guess."""

    PURPOSES = [
        ("evaluate", "Evaluate match"), ("tailor", "Tailor CV"), ("prep", "Prep plan"),
        ("interview_prep", "Interview questions"), ("answer_feedback", "Answer feedback"), ("app_answer", "Application answer"),
        ("summarise", "Posting summary"), ("suggest_roles", "Role suggestions"), ("message_draft", "Message draft"),
        ("parse_posting", "Posting reader"), ("counter_note", "Counter-offer note"), ("referral_draft", "Referral message"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_usage_events")
    application = models.ForeignKey(Application, null=True, blank=True, on_delete=models.SET_NULL, related_name="ai_usage_events")
    created_at = models.DateTimeField(auto_now_add=True)
    provider = models.CharField(max_length=20)
    purpose = models.CharField(max_length=24, choices=PURPOSES)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    cost_is_estimate = models.BooleanField(default=True, help_text="False only when the provider itself reported the cost.")
    model = models.CharField(max_length=80, blank=True, help_text="The model that answered, when known. Blank on older events.")
    duration_ms = models.PositiveIntegerField(null=True, blank=True, help_text="How long the call took. Blank on older events.")
    ok = models.BooleanField(default=True, help_text="False when the call failed (no answer came back).")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} {self.purpose} {self.created_at:%Y-%m-%d}"
        constraints = [models.UniqueConstraint(fields=["posting", "seen_date"], name="uniq_posting_seen_date")]


class InterviewPrep(models.Model):
    """The latest interview questions made for one job (replaced when the person asks again). Suggestions only: the person reads and rewrites them."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interview_preps")
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="interview_prep")
    content = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Interview questions for {self.application}"


from .google_models import GoogleConnection, MailMessage  # noqa: E402,F401  (registers them with the app)
from .prep_models import PrepAnswer, PrepChallenge, PrepChallengeItem, PrepLesson, PrepMilestone, PrepPlan, PrepQuestion, PrepTopic, PrepWeek  # noqa: E402,F401  (registers them with the app)


class RefineMessage(models.Model):
    """One line of the "Ask for changes" chat on a CV version or a cover letter: the person's instruction, or a one-sentence summary
    of what the AI changed. Text only and short; the panel shows earlier turns from here. Owner-only, like the document it belongs to."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refine_messages")
    cv_version = models.ForeignKey(CVVersion, null=True, blank=True, on_delete=models.CASCADE, related_name="refine_messages", help_text="The version the instruction was given on.")
    cover_letter = models.ForeignKey(CoverLetter, null=True, blank=True, on_delete=models.CASCADE, related_name="refine_messages")
    role = models.CharField(max_length=10, choices=[("user", "Person"), ("assistant", "AI")])
    text = models.CharField(max_length=700)
    result_version = models.ForeignKey(CVVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", help_text="The new CV version this answer made.")
    flagged_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class CoverLetterRevision(models.Model):
    """What a cover letter said before the AI changed it (or before an undo), so a change can be taken back. A letter is edited in
    place, so this small list is its history; rows are only ever added (the oldest ones are trimmed past a cap)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cover_revisions")
    letter = models.ForeignKey(CoverLetter, on_delete=models.CASCADE, related_name="revisions")
    content = models.TextField()
    source = models.CharField(max_length=10, blank=True)
    check_report = models.JSONField(default=list, blank=True)
    reason = models.CharField(max_length=10, choices=[("refine", "Before an AI change"), ("undo", "Before going back")], default="refine")
    undone = models.BooleanField(default=False, help_text="Already taken back, so Undo skips it.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Notification(models.Model):
    """One short in-app notice for one person (the bell in the header). Made by code that already knows the event happened (a finished
    search, a follow-up that fell due...), never by the person's own text. `link` is an internal app path only. `dedupe_key` makes a
    producer safe to run again (the same deadline is announced once); `cleared` hides a notice without forgetting it was made, so
    clearing does not bring it back. At most NOTIFICATION_CAP per person are kept, the oldest dropped."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20)
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=300, blank=True)
    link = models.CharField(max_length=200, blank=True)
    dedupe_key = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    cleared = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["owner", "-created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["owner", "dedupe_key"], condition=~models.Q(dedupe_key=""), name="uniq_notification_dedupe"),
        ]

    def __str__(self):
        return f"{self.kind}: {self.title}"
