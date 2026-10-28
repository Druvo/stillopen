"""Django settings. Everything environment-specific comes from env vars or .env."""
import os
import secrets
import sys
from pathlib import Path

from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE lines); real environment variables win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _secret_key() -> str:
    env = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if env:
        return env
    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(64)
    key_file.write_text(key, encoding="utf-8")
    return key


SECRET_KEY = _secret_key()
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
if "127.0.0.1" not in ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("127.0.0.1")  # the container's own health check calls it by this address, whatever public host name is set
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "unfold",  # must come before django.contrib.admin to replace its templates
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "allauth.socialaccount.providers.facebook",
    "tracker",
    "django.forms",  # needed for FORM_RENDERER = TemplatesSetting to find Django's own built-in widget templates
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tracker.context.site_config",
            ],
        },
    },
]

# Django's default form renderer uses its own template engine scoped to django.forms' own
# templates, ignoring TEMPLATES[0]["DIRS"] above -- so templates/django/forms/widgets/*.html
# (the Tabler/Bootstrap checkbox-list markup override) would silently never be found without this.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# django-unfold: the admin's look (a modern Tailwind skin, light and dark). Everything it needs (fonts, icons, scripts) is served by
# this app itself, nothing comes from a third-party host (tests/tests_selfhost.py checks the admin pages too).
UNFOLD = {
    "SITE_TITLE": "StillOpen admin",
    "SITE_HEADER": "StillOpen",
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    # The sidebar leads with what an owner actually needs, not an alphabetical list of every app.
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {"title": "Settings", "items": [
                {"title": "Site configuration", "icon": "tune", "link": reverse_lazy("admin:tracker_siteconfig_changelist")},
                {"title": "Job sources", "icon": "travel_explore", "link": reverse_lazy("admin:tracker_jobsource_changelist")},
                {"title": "Postings seen", "icon": "work", "link": reverse_lazy("admin:tracker_posting_changelist")},
            ]},
            {"title": "People", "items": [
                {"title": "Users", "icon": "group", "link": reverse_lazy("admin:auth_user_changelist")},
                {"title": "Profiles", "icon": "badge", "link": reverse_lazy("admin:tracker_userprofile_changelist")},
                {"title": "Applications", "icon": "assignment", "link": reverse_lazy("admin:tracker_application_changelist")},
                {"title": "Documents", "icon": "description", "link": reverse_lazy("admin:tracker_knowledgesource_changelist")},
            ]},
            {"title": "Activity", "items": [
                {"title": "Searches run", "icon": "search", "link": reverse_lazy("admin:tracker_scanrun_changelist")},
                {"title": "Open/closed checks", "icon": "fact_check", "link": reverse_lazy("admin:tracker_livenessrun_changelist")},
                {"title": "AI usage", "icon": "smart_toy", "link": reverse_lazy("admin:tracker_aiusageevent_changelist")},
            ]},
            {"title": "Labels and wording", "items": [
                {"title": "Dashboard tabs", "icon": "tab", "link": reverse_lazy("admin:tracker_bucket_changelist")},
                {"title": "Statuses", "icon": "label", "link": reverse_lazy("admin:tracker_status_changelist")},
                {"title": "Score bands", "icon": "stacked_bar_chart", "link": reverse_lazy("admin:tracker_scoreband_changelist")},
                {"title": "Job sites by link", "icon": "link", "link": reverse_lazy("admin:tracker_source_changelist")},
                {"title": "Expired phrases", "icon": "event_busy", "link": reverse_lazy("admin:tracker_expiredphrase_changelist")},
                {"title": "Document kinds", "icon": "folder", "link": reverse_lazy("admin:tracker_documentkind_changelist")},
            ]},
            {"title": "Sign-in and access", "items": [
                {"title": "Groups", "icon": "shield_person", "link": reverse_lazy("admin:auth_group_changelist")},
                {"title": "Email addresses", "icon": "mail", "link": reverse_lazy("admin:account_emailaddress_changelist")},
                {"title": "Two-step devices", "icon": "key", "link": reverse_lazy("admin:mfa_authenticator_changelist")},
                {"title": "Linked social accounts", "icon": "share", "link": reverse_lazy("admin:socialaccount_socialaccount_changelist")},
                {"title": "Social applications", "icon": "apps", "link": reverse_lazy("admin:socialaccount_socialapp_changelist")},
                {"title": "Sites", "icon": "language", "link": reverse_lazy("admin:sites_site_changelist")},
            ]},
        ],
    },
    "COLORS": {
        "primary": {
            "50": "239 246 255", "100": "219 234 254", "200": "191 219 254", "300": "147 197 253", "400": "96 165 250",
            "500": "59 130 246", "600": "37 99 235", "700": "29 78 216", "800": "30 64 175", "900": "30 58 138", "950": "23 37 84",
        },
    },
}

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("STILLOPEN_DB", str(BASE_DIR / "db.sqlite3")),
    }
}
# Shared hosting: set DATABASE_URL (e.g. postgres://user:pass@host:5432/stillopen). Needs requirements-hosting.txt.
if os.environ.get("DATABASE_URL"):
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=60)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Dhaka")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Vendored front-end files (Tabler) live here and are served by this app, never from a third-party CDN.
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = DEBUG

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("STILLOPEN_MEDIA", str(BASE_DIR / "media")))
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/app/"
LOGOUT_REDIRECT_URL = "/"

# Registration is controlled from the admin (Site configuration > Sign-up: closed or open).
# Open sign-up needs a verified email, so configure SMTP (EMAIL_HOST...) before opening it; without SMTP the
# verification link is printed to the server console.
ACCOUNT_LOGIN_METHODS = {"username", "email"}
# Email and a password is all we ask for; a username is made up from the email (it can still be used to sign in).
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_CONFIRM_EMAIL_ON_GET = True  # the link in the email is the whole confirmation, no second button
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True  # and it signs the person in
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
# "optional" globally so accounts made in the admin or by createsuperuser (no confirmed email) are never locked out;
# tracker.auth.AccountAdapter.pre_login makes confirmation mandatory for accounts created through the sign-up form.
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_FORMS = {"signup": "tracker.forms.SignupForm"}
# Bot protection without any third-party service (the no-CDN rule): a hidden trap field, a minimum time to fill the
# sign-up form (0 turns the timing check off), and per-IP rate limits. Behind a reverse proxy set
# ALLAUTH_TRUSTED_PROXY_COUNT (e.g. 1) so the limits see the visitor's address and not the proxy's.
STILLOPEN_SIGNUP_MIN_SECONDS = int(os.environ.get("STILLOPEN_SIGNUP_MIN_SECONDS", "3"))
ACCOUNT_RATE_LIMITS = {
    "signup": os.environ.get("STILLOPEN_SIGNUP_RATE", "5/h/ip"),
    "login_failed": os.environ.get("STILLOPEN_LOGIN_FAILED_RATE", "10/10m/ip,5/5m/key"),
}
ALLAUTH_TRUSTED_PROXY_COUNT = int(os.environ.get("ALLAUTH_TRUSTED_PROXY_COUNT", "0"))
ACCOUNT_PASSWORD_MIN_LENGTH = 10
# Two-step sign-in, optional and per person (Profile > Your account > Two-step sign-in): an authenticator app, a hardware security
# key or passkey as a second step, and one-time recovery codes. Runs entirely in this app, no third-party service.
MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_TOTP_ISSUER = os.environ.get("STILLOPEN_TOTP_ISSUER", "StillOpen")
# Without SMTP (a common self-host setup) nobody has a verified email, and allauth would then refuse to let anyone turn this on.
# Sign-ups that go through the email step are already confirmed before they can sign in.
MFA_ALLOW_UNVERIFIED_EMAIL = True
MFA_PASSKEY_LOGIN_ENABLED = False
MFA_PASSKEY_SIGNUP_ENABLED = False
# Email goes through whatever is set up at the moment of sending: these environment variables if EMAIL_HOST is set, otherwise the
# admin's Site configuration > Email sending, otherwise the server console (tracker/email_backend.py, services/integrations.py).
EMAIL_BACKEND = "tracker.email_backend.ConfiguredBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "StillOpen <noreply@localhost>")
EMAIL_CONFIGURED = bool(os.environ.get("EMAIL_HOST"))
# People who register themselves must click an emailed link before they get in -- but only where that email can actually
# arrive. With no SMTP the link would only be printed to the server console and nobody could ever sign up, so a fresh
# self-hosted install lets people straight in and tells the admin (see the dashboard notice). Set to 1 to insist anyway.
# None means "decide at the moment": on once email is set up (here or in the admin), off while it is not.
if os.environ.get("STILLOPEN_REQUIRE_EMAIL_CONFIRMATION") is not None:
    STILLOPEN_REQUIRE_EMAIL_CONFIRMATION = os.environ["STILLOPEN_REQUIRE_EMAIL_CONFIRMATION"] == "1"
elif EMAIL_CONFIGURED or "test" in sys.argv:
    STILLOPEN_REQUIRE_EMAIL_CONFIRMATION = True
else:
    STILLOPEN_REQUIRE_EMAIL_CONFIRMATION = None
# "optional" globally so accounts made in the admin or by createsuperuser (no confirmed email) are never locked out;
# tracker.auth.AccountAdapter.pre_login makes confirmation mandatory for accounts created through the sign-up form.
# "none" when confirmation is not required, so no email is sent (or claimed to be sent) from a server that cannot send it.
ACCOUNT_EMAIL_VERIFICATION = os.environ.get("ACCOUNT_EMAIL_VERIFICATION", "none" if STILLOPEN_REQUIRE_EMAIL_CONFIRMATION is False else "optional")

# Per-person limits on a shared server.
STILLOPEN_MAX_APPLICATIONS = int(os.environ.get("STILLOPEN_MAX_APPLICATIONS", "500"))
STILLOPEN_MAX_KNOWLEDGE = int(os.environ.get("STILLOPEN_MAX_KNOWLEDGE", "40"))
# Where the built new app (Next.js static export) lives; /app/ answers 404 until it has been built.
# A strict Content-Security-Policy on the new app's page (scripts only from this site and the build's own inline scripts, by hash). "0" turns it off.
STILLOPEN_APP_CSP = os.environ.get("STILLOPEN_APP_CSP", "1") == "1"
STILLOPEN_FRONTEND_DIR = os.environ.get("STILLOPEN_FRONTEND_DIR", str(BASE_DIR / "frontend" / "out"))
STILLOPEN_EVALS_PER_HOUR = int(os.environ.get("STILLOPEN_EVALS_PER_HOUR", "30"))
STILLOPEN_CHECKS_PER_HOUR = int(os.environ.get("STILLOPEN_CHECKS_PER_HOUR", "12"))
STILLOPEN_SCANS_PER_HOUR = int(os.environ.get("STILLOPEN_SCANS_PER_HOUR", "6"))
STILLOPEN_QUICKADD_PER_HOUR = int(os.environ.get("STILLOPEN_QUICKADD_PER_HOUR", "30"))
# The public, no-sign-in tools (/tools/...): per-IP, since nobody is signed in to rate-limit by account.
STILLOPEN_PUBLIC_TOOL_RATE_PER_HOUR = int(os.environ.get("STILLOPEN_PUBLIC_TOOL_RATE_PER_HOUR", "20"))
STILLOPEN_PUBLIC_TOOL_MIN_SECONDS = int(os.environ.get("STILLOPEN_PUBLIC_TOOL_MIN_SECONDS", "2"))
# How many of the candidate's own skill terms a posting's title+blurb must share to be added even when its
# title doesn't literally contain one of their target-role phrases. Higher = fewer false positives.
STILLOPEN_SKILL_MATCH_MIN_OVERLAP = int(os.environ.get("STILLOPEN_SKILL_MATCH_MIN_OVERLAP", "4"))
# Interviews, contacts, referrals and offers: most any one person may save of each.
# Job search engine. Reading each source's public list is shared between everyone's searches for this long (public
# feeds ask for few requests a day), sources are read this many at a time, and one search adds at most this many
# new jobs (the best matches first; the rest stay under All postings). Tests turn the cache and the seeded default
# sources off so they stay deterministic.
RUNNING_TESTS = "test" in sys.argv
STILLOPEN_SCAN_CACHE_SECONDS = int(os.environ.get("STILLOPEN_SCAN_CACHE_SECONDS", "0" if RUNNING_TESTS else "21600"))
STILLOPEN_SCAN_FETCH_THREADS = int(os.environ.get("STILLOPEN_SCAN_FETCH_THREADS", "16"))
# Longest a search waits for the job sources (a slow one is skipped, not waited for).
STILLOPEN_SCAN_DEADLINE_SECONDS = int(os.environ.get("STILLOPEN_SCAN_DEADLINE_SECONDS", "60"))
# At most this many new jobs from one employer per search (big employers post the same role for every team), and
# a word counts as generic filler, not a skill, when it appears in more than this share of all postings read.
STILLOPEN_SCAN_MAX_PER_COMPANY = int(os.environ.get("STILLOPEN_SCAN_MAX_PER_COMPANY", "5"))
STILLOPEN_SCAN_GENERIC_SHARE = float(os.environ.get("STILLOPEN_SCAN_GENERIC_SHARE", "0.12"))
# A posting needs at least this many distinct words before it is scored: three words cannot tell anyone how well they fit.
STILLOPEN_SCAN_MIN_TERMS_TO_SCORE = int(os.environ.get("STILLOPEN_SCAN_MIN_TERMS_TO_SCORE", "12"))
# A search starts as soon as this many seconds have passed with most sources answered (a few slow hosts are waited for
# afterwards and topped up), and its first batch adds at most this many jobs so something shows up quickly.
STILLOPEN_SCAN_FIRST_WAIT_SECONDS = int(os.environ.get("STILLOPEN_SCAN_FIRST_WAIT_SECONDS", "15"))
STILLOPEN_SCAN_FIRST_BATCH = int(os.environ.get("STILLOPEN_SCAN_FIRST_BATCH", "25"))
# The public job board: an opening nobody has seen for this many days is treated as gone; the board refreshes itself when a visitor
# arrives and it is older than this many hours (or run `manage.py refresh_postings` from cron); public pages are cached this long.
STILLOPEN_PUBLIC_ACTIVE_DAYS = int(os.environ.get("STILLOPEN_PUBLIC_ACTIVE_DAYS", "3"))
STILLOPEN_PUBLIC_REFRESH_HOURS = int(os.environ.get("STILLOPEN_PUBLIC_REFRESH_HOURS", "6"))
STILLOPEN_PUBLIC_AUTO_REFRESH = os.environ.get("STILLOPEN_PUBLIC_AUTO_REFRESH", "0" if RUNNING_TESTS else "1") == "1"
STILLOPEN_PUBLIC_CACHE_SECONDS = int(os.environ.get("STILLOPEN_PUBLIC_CACHE_SECONDS", "0" if RUNNING_TESTS else "300"))
STILLOPEN_PUBLIC_PAGE_SIZE = int(os.environ.get("STILLOPEN_PUBLIC_PAGE_SIZE", "30"))
STILLOPEN_SCAN_MAX_NEW = int(os.environ.get("STILLOPEN_SCAN_MAX_NEW", "40"))
# Most tailored CV drafts one scheduled search prepares for one person ("Draft ahead", Profile > Job alerts).
STILLOPEN_DRAFT_AHEAD_MAX = int(os.environ.get("STILLOPEN_DRAFT_AHEAD_MAX", "3"))
STILLOPEN_AUTO_SCAN = os.environ.get("STILLOPEN_AUTO_SCAN", "0" if RUNNING_TESTS else "1") == "1"
STILLOPEN_SEED_SOURCES = os.environ.get("STILLOPEN_SEED_SOURCES", "0" if RUNNING_TESTS else "1") == "1"
# Company job boards one person may add for their own searches, and how many they may add per hour.
STILLOPEN_MAX_OWN_SOURCES = int(os.environ.get("STILLOPEN_MAX_OWN_SOURCES", "20"))
# Web MCP endpoint (/mcp/): personal tokens, per person limits.
STILLOPEN_MAX_API_TOKENS = int(os.environ.get("STILLOPEN_MAX_API_TOKENS", "10"))
STILLOPEN_TOKEN_ISSUES_PER_HOUR = int(os.environ.get("STILLOPEN_TOKEN_ISSUES_PER_HOUR", "10"))
STILLOPEN_MCP_CALLS_PER_MINUTE = int(os.environ.get("STILLOPEN_MCP_CALLS_PER_MINUTE", "120"))
STILLOPEN_MCP_BAD_TOKENS_PER_MINUTE = int(os.environ.get("STILLOPEN_MCP_BAD_TOKENS_PER_MINUTE", "20"))
STILLOPEN_SOURCE_ADDS_PER_HOUR = int(os.environ.get("STILLOPEN_SOURCE_ADDS_PER_HOUR", "20"))
STILLOPEN_MAX_PIPELINE = int(os.environ.get("STILLOPEN_MAX_PIPELINE", "500"))
STILLOPEN_MAX_CV_VERSIONS = int(os.environ.get("STILLOPEN_MAX_CV_VERSIONS", "200"))
STILLOPEN_CVGEN_PER_HOUR = int(os.environ.get("STILLOPEN_CVGEN_PER_HOUR", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
ACCOUNT_ADAPTER = "tracker.auth.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "tracker.auth.SocialAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = False  # sign-in starts with a CSRF-protected POST
# A verified Google email is attached to the existing local user with that email (the owner).
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "VERIFIED_EMAIL": True,
    },
    # GitHub reports which of a person's addresses it has verified; only a verified one is ever trusted.
    "github": {"SCOPE": ["read:user", "user:email"]},
    # Facebook's email is not treated as verified: a new person confirms it by the usual email link, and it is never
    # used to attach to somebody else's existing account.
    "facebook": {
        "METHOD": "oauth2",
        "SCOPE": ["email", "public_profile"],
        "FIELDS": ["id", "email", "name", "first_name", "last_name"],
        "VERIFIED_EMAIL": False,
    },
}
# Optional: configure a provider from the environment instead of the admin "Social applications" page.
for _provider in ("google", "github", "facebook"):
    if os.environ.get(f"{_provider.upper()}_CLIENT_ID") and os.environ.get(f"{_provider.upper()}_CLIENT_SECRET"):
        SOCIALACCOUNT_PROVIDERS[_provider]["APP"] = {
            "client_id": os.environ[f"{_provider.upper()}_CLIENT_ID"],
            "secret": os.environ[f"{_provider.upper()}_CLIENT_SECRET"],
            "key": "",
        }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The per-person rate limits (and the search-source cache) live in Django's cache. The default, LocMemCache,
# is per-process memory -- fine for the one-process-per-machine setup docs/HOSTING.md describes, but it means
# running more than one gunicorn worker (or more than one machine) splits those counters, so a limit meant to
# be site-wide becomes "site-wide per worker". Set REDIS_URL to share the cache across every process/machine;
# unset, nothing changes from before. Needs requirements-redis.txt.
_redis_url = os.environ.get("REDIS_URL", "").strip()
if _redis_url:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _redis_url}}

# Seeds for SiteConfig on first migrate (editable later in the admin).
CAREEROPS_PATH_DEFAULT = os.environ.get("CAREEROPS_PATH", "")
NODE_COMMAND_DEFAULT = os.environ.get("NODE_COMMAND", "node")
PAPERLESS_URL_DEFAULT = os.environ.get("PAPERLESS_URL", "")

if not DEBUG:
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = False  # the dashboard JS reads the CSRF cookie
    SECURE_CONTENT_TYPE_NOSNIFF = True
    if os.environ.get("DJANGO_HTTPS", "1") == "1":  # set DJANGO_HTTPS=0 only for plain-http testing
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
        SECURE_HSTS_SECONDS = 31536000
        SECURE_REFERRER_POLICY = "same-origin"
    if os.environ.get("DJANGO_BEHIND_PROXY") == "1":  # nginx/Caddy terminates TLS and sets X-Forwarded-Proto
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Optional: error tracking. GlitchTip (self-hosted, open-source) speaks the same DSN/API as Sentry, so the
# official sentry-sdk works against either -- point GLITCHTIP_DSN (or SENTRY_DSN) at your own instance.
# Off by default: nothing is sent anywhere unless one of these is set. Needs requirements-errors.txt.
_error_tracking_dsn = os.environ.get("GLITCHTIP_DSN") or os.environ.get("SENTRY_DSN")
if _error_tracking_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_error_tracking_dsn,
        integrations=[DjangoIntegration()],
        environment=os.environ.get("STILLOPEN_ENVIRONMENT", "production" if not DEBUG else "development"),
        traces_sample_rate=float(os.environ.get("GLITCHTIP_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,  # job descriptions and CV text are untrusted/personal data; never attach request bodies
    )
