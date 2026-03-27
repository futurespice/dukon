from decouple import config, UndefinedValueError

from .base import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ['*']

CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Database — safe defaults only in local development.
# AUDIT SECURITY FIX: base.py now requires DB_USER and DB_PASSWORD with no
# defaults. In local dev we provide the common postgres/postgres fallback here
# so developers can run `manage.py migrate` without a full .env file.
# This block is NOT imported in production.py.
# ---------------------------------------------------------------------------
try:
    config('DB_USER')  # already set — base.py will use it
except UndefinedValueError:
    import os
    os.environ.setdefault('DB_USER', 'postgres')
    os.environ.setdefault('DB_PASSWORD', 'postgres')

# AUDIT-3 DEVOPS FIX #11: django-extensions only in dev settings.
try:
    import django_extensions  # noqa: F401
    INSTALLED_APPS += ['django_extensions']  # noqa: F405
except ImportError:
    pass

# In local dev, show all codes in logs instead of actually sending messages
# GREENAPI_* can be empty — DEBUG mode in tasks.py skips real sending.
