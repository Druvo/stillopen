"""Django settings. Everything environment-specific comes from env vars or .env."""
import os
import secrets
from pathlib import Path

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
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "jazzmin",  # must come before django.contrib.admin to replace its templates
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
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

# django-jazzmin: Bootstrap-based admin skin so /admin/ matches the Tabler/Bootstrap theme of the rest
# of the app, instead of stock Django admin's unrelated look.
JAZZMIN_SETTINGS = {
    "site_title": "StillOpen admin",
    "site_header": "StillOpen",
    "site_brand": "StillOpen admin",
    "welcome_sign": "Sign in to the StillOpen admin",
    "copyright": "StillOpen",
    "show_sidebar": True,
    "navigation_expanded": False,
    "changeform_format": "horizontal_tabs",
    "use_google_fonts_cdn": False,  # no third-party requests from the admin either
}
JAZZMIN_UI_TWEAKS = {
    "theme": "darkly",
    "default_theme_mode": "dark",
    "navbar": "navbar-dark",
    "no_navbar_border": True,
    "sidebar": "sidebar-dark-primary",
    "brand_colour": "navbar-primary",
    "accent": "accent-primary",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
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
LOGIN_REDIRECT_URL = "/dashboard/"
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
ACCOUNT_EMAIL_VERIFICATION = os.environ.get("ACCOUNT_EMAIL_VERIFICATION", "optional")
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_PASSWORD_MIN_LENGTH = 10
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "StillOpen <noreply@localhost>")

# Per-person limits on a shared server.
STILLOPEN_MAX_APPLICATIONS = int(os.environ.get("STILLOPEN_MAX_APPLICATIONS", "500"))
STILLOPEN_MAX_KNOWLEDGE = int(os.environ.get("STILLOPEN_MAX_KNOWLEDGE", "40"))
STILLOPEN_EVALS_PER_HOUR = int(os.environ.get("STILLOPEN_EVALS_PER_HOUR", "30"))
STILLOPEN_CHECKS_PER_HOUR = int(os.environ.get("STILLOPEN_CHECKS_PER_HOUR", "12"))
STILLOPEN_SCANS_PER_HOUR = int(os.environ.get("STILLOPEN_SCANS_PER_HOUR", "6"))
STILLOPEN_QUICKADD_PER_HOUR = int(os.environ.get("STILLOPEN_QUICKADD_PER_HOUR", "30"))
# How many of the candidate's own skill terms a posting's title+blurb must share to be added even when its
# title doesn't literally contain one of their target-role phrases. Higher = fewer false positives.
STILLOPEN_SKILL_MATCH_MIN_OVERLAP = int(os.environ.get("STILLOPEN_SKILL_MATCH_MIN_OVERLAP", "4"))
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
    }
}
# Optional: configure Google from the environment instead of the admin "Social applications" page.
if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
    SOCIALACCOUNT_PROVIDERS["google"]["APP"] = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "key": "",
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
