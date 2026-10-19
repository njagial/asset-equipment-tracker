"""Development settings.

Uses Dockerized Postgres/Redis when DATABASE_URL / CELERY_BROKER_URL are set;
otherwise falls back to a local sqlite file so the app still boots without
Docker on a laptop.
"""
from .base import *

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if not os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.path.join(BASE_DIR, "dev.sqlite3")}
    }
