"""
Django settings for the K8s Manager backend.

Design notes (see README for full rationale):
- Config is fully environment-driven so the same image runs unmodified in
  dev / staging / production (12-factor), which matters once this is built
  as a container and deployed onto the k3s cluster it manages.
- Postgres is used via DATABASE_URL when set; falls back to sqlite for
  quick local dev. Postgres is what you want once you scale to multiple
  backend replicas, since sqlite cannot be shared across pods.
- Cluster tokens are encrypted at rest (see core.encryption) - the Fernet
  key is supplied via env/secret, never committed.
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

if not DEBUG:
    if SECRET_KEY == "dev-only-insecure-key-change-me":
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG=False")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise RuntimeError(
            "DJANGO_ALLOWED_HOSTS must contain explicit hosts when DJANGO_DEBUG=False"
        )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "corsheaders",
    "django_filters",
    # local apps
    "core",
    "clusters",
    "namespaces",
    "workloads",
    # local backups app (provides backup API + Celery tasks)
    "backups",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

if not DEBUG and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set when DJANGO_DEBUG=False")

# ---------------------------------------------------------------------------
# Passwords / auth
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# I18N
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# CORS (frontend will be a separate app/origin)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "False") == "True"
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    # Per the assignment: protect write endpoints against a client hammering
    # create/delete in a tight loop. Scopes are attached per-view via
    # `throttle_scope`. Tune these per environment.
    "DEFAULT_THROTTLE_RATES": {
        "cluster-write": "30/min",
        "namespace-write": "20/min",
        "app-write": "30/min",
    },
}

if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
        "rest_framework.renderers.BrowsableAPIRenderer"
    )

# ---------------------------------------------------------------------------
# App-specific settings
# ---------------------------------------------------------------------------

# Fernet key for encrypting Cluster.token at rest. MUST be set in real
# environments via secret/env var - never commit a real key.
FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")
if not DEBUG and not FIELD_ENCRYPTION_KEY:
    raise RuntimeError("FIELD_ENCRYPTION_KEY must be set when DJANGO_DEBUG=False")

# Kubernetes client behaviour
K8S_VERIFY_SSL = os.environ.get("K8S_VERIFY_SSL", "False") == "True"
K8S_CA_CERT_PATH = os.environ.get("K8S_CA_CERT_PATH") or None
K8S_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("K8S_REQUEST_TIMEOUT_SECONDS", "10"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_tokens": {"()": "core.logging_filters.RedactTokenFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["redact_tokens"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Never let the kubernetes client's debug logging leak bearer tokens.
        "kubernetes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Celery / background tasks
# ---------------------------------------------------------------------------
# Broker and result backend (default to local redis at 6379)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")

# Directory to store generated backups (relative to project base dir)
BACKUPS_DIR = Path(os.environ.get("BACKUPS_DIR", BASE_DIR / "backups"))
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Optional S3 upload settings for backups
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
AWS_S3_REGION = os.environ.get("AWS_S3_REGION")
AWS_S3_KEY_PREFIX = os.environ.get("AWS_S3_KEY_PREFIX", "")
BACKUP_REMOTE_REQUIRED = os.environ.get(
    "BACKUP_REMOTE_REQUIRED", "False" if DEBUG else "True"
) == "True"
