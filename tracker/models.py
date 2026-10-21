import os
from datetime import date
from urllib.parse import urlparse

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from . import crypto


class SiteConfig(models.Model):
    """Single-row configuration, edited in the admin."""

    LIVENESS_MODES = [
        ("http", "Built-in HTTP check (looks for the expiry phrases below)"),
        ("node", "career-ops checker (Playwright, handles JavaScript sites)"),
    ]

    site_title = models.CharField(max_length=80, default="StillOpen")
    score_scale = models.FloatField(
        default=5.0,
        validators=[MinValueValidator(1.0)],
        help_text="Top of the score range used by evaluations. Match % = score / this x 100.",
    )
    urgent_days = models.PositiveIntegerField(
        default=7, help_text="Deadlines within this many days are highlighted and sorted first."
    )
    auto_close_expired = models.BooleanField(
        default=True,
        help_text="Show applications whose posting is confirmed expired under the closed tab (unless already applied).",
    )

    careerops_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Folder of your career-ops project (reads data/applications.md, reports/, output/).",
    )
    node_command = models.CharField(max_length=200, default="node", help_text="Command used to run career-ops scripts.")

    liveness_mode = models.CharField(max_length=10, choices=LIVENESS_MODES, default="http")
    liveness_timeout = models.PositiveIntegerField(default=60, help_text="Seconds allowed per posting check.")

    paperless_enabled = models.BooleanField(default=False)
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
            "Who may sign in with Google, one per line: a full address (you@gmail.com) or a whole domain (@company.com). "
            "Everyone listed can see all jobs and documents. Empty means nobody new can sign in. "
            "An existing user with the same verified email can always sign in."
        ),
    )

    AI_PROVIDERS = [
        ("none", "Off (free keyword match only)"),
        ("anthropic", "Anthropic API key"),
        ("openai", "OpenAI-compatible API (OpenAI, OpenRouter, Groq, Mistral, Gemini, DeepSeek, Ollama, LM Studio...)"),
        ("custom_http", "Custom HTTP API (any provider: you describe the request and where the answer is)"),
        ("claude_cli", "Claude Code CLI installed on this machine"),
        ("agent_sdk", "Claude Agent SDK (pip install -r requirements-ai.txt)"),
    ]
    ai_provider = models.CharField(max_length=12, choices=AI_PROVIDERS, default="none")
    ai_model = models.CharField(max_length=100, blank=True, help_text="Leave blank for the provider's default.")
    ai_base_url = models.CharField(
        max_length=300,
        blank=True,
        help_text=(
            "OpenAI-compatible: the API base, e.g. http://127.0.0.1:11434/v1 (Ollama), https://openrouter.ai/api/v1, "
            "https://api.groq.com/openai/v1, https://api.mistral.ai/v1, "
            "https://generativelanguage.googleapis.com/v1beta/openai (Gemini). "
            "Custom HTTP: the full endpoint URL."
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
        help_text="Your CV as plain text. Sent to the AI provider you choose. Blank = read cv.md from the career-ops folder.",
    )
    profile_preferences = models.TextField(
        blank=True, help_text="What you want: target roles, locations, remote, salary floor, deal-breakers."
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

    class Meta:
        verbose_name = "Site configuration"
        verbose_name_plural = "Site configuration"

    def __str__(self):
        return "Site configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # singleton
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

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

    def set_ai_key(self, plain: str) -> None:
        self.ai_key_encrypted = crypto.encrypt(plain.strip())

    @property
    def effective_ai_key(self) -> str:
        return os.environ.get("STILLOPEN_AI_API_KEY", "").strip() or crypto.decrypt(self.ai_key_encrypted)

    @property
    def effective_profile_cv(self) -> str:
        if self.profile_cv.strip():
            return self.profile_cv
        if self.careerops_path:
            cv = os.path.join(self.careerops_path, "cv.md")
            if os.path.isfile(cv):
                with open(cv, encoding="utf-8") as fh:
                    return fh.read()
        return ""

    @property
    def effective_paperless_token(self):
        return os.environ.get("PAPERLESS_TOKEN", "").strip() or self.paperless_token.strip()

    @property
    def effective_paperless_url(self):
        return (os.environ.get("PAPERLESS_URL", "").strip() or self.paperless_url.strip()).rstrip("/")


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
    LIVE = [
        ("unknown", "Not checked"),
        ("active", "Open"),
        ("expired", "Closed"),
        ("uncertain", "Unclear"),
    ]

    careerops_num = models.PositiveIntegerField(null=True, blank=True, unique=True, help_text="Row # in the career-ops tracker.")
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
    ai_evaluated_at = models.DateTimeField(null=True, blank=True)
    ai_method = models.CharField(max_length=40, blank=True)

    live_state = models.CharField(max_length=10, choices=LIVE, default="unknown")
    live_detail = models.CharField(max_length=300, blank=True)
    live_checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-careerops_num", "-id"]

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


class LivenessRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    running = models.BooleanField(default=True)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
