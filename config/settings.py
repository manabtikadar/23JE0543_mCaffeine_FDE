import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
TIME_ZONE = "UTC"
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "orders",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.contrib.auth.context_processors.auth"]},
}]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "orders.access.require_api_session",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
ALLOWED_HOSTS = [render_hostname] if render_hostname else ["localhost", "127.0.0.1", "[::1]"]
if render_hostname:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # Render's internal health probe must reach the database check over HTTP too.
    SECURE_REDIRECT_EXEMPT = [r"^health$"]
    SECURE_HSTS_SECONDS = 31536000
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

database = dj_database_url.parse(os.environ["DATABASE_URL"])
if database["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("DATABASE_URL must select PostgreSQL.")
options = database.setdefault("OPTIONS", {})
options.setdefault("sslmode", "require")
if render_hostname and options["sslmode"] not in {"require", "verify-ca", "verify-full"}:
    raise ImproperlyConfigured("The deployed database connection requires TLS.")
options["connect_timeout"] = 3
DATABASES = {"default": database}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"timestamped": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "timestamped"}},
    "loggers": {
        "config": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
