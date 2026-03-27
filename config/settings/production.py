from decouple import config

from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='back.dukon.online').split(',')

# ---------------------------------------------------------------------------
# HTTPS hardening
# ---------------------------------------------------------------------------

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
# AUDIT #6 (CRITICAL): Without this, Django behind nginx/ALB can't detect
# HTTPS from X-Forwarded-Proto, causing infinite redirect loops.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# Database — persistent connections in production
# ---------------------------------------------------------------------------

DATABASES['default']['CONN_MAX_AGE'] = 60  # noqa: F821

# ---------------------------------------------------------------------------
# Redis — password-protected in production (DEVOPS FIX #7)
# REDIS_URL is injected by docker-compose as redis://:PASSWORD@redis:6379/0
# The base.py REDIS_URL already reads from env, so no override needed here
# unless you need to guarantee the password is enforced at the settings layer.
# ---------------------------------------------------------------------------

_redis_password = config('REDIS_PASSWORD', default='')
if _redis_password:
    # Override the base REDIS_URL to include the password.
    # This ensures Celery and django-redis both use authenticated connections
    # even if REDIS_URL in .env was accidentally left without credentials.
    REDIS_URL = f'redis://:{_redis_password}@{config("REDIS_HOST", default="redis")}:6379/0'  # noqa: F821
    CACHES['default']['LOCATION'] = REDIS_URL  # noqa: F821
    CELERY_BROKER_URL = REDIS_URL  # noqa: F821
    CELERY_RESULT_BACKEND = REDIS_URL  # noqa: F821

# ---------------------------------------------------------------------------
# CORS — explicit allowlist in production
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = False

# ---------------------------------------------------------------------------
# Swagger — admin-only in production
# ---------------------------------------------------------------------------

SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] = [  # noqa: F821
    'rest_framework.permissions.IsAdminUser',
]
