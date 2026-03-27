from decouple import config

from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='beurer.kg,www.beurer.kg').split(',')

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r'^health/$']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

DATABASES['default']['CONN_MAX_AGE'] = 60  # noqa: F821

_redis_password = config('REDIS_PASSWORD', default='')
if _redis_password:
    REDIS_URL = f'redis://:{_redis_password}@{config("REDIS_HOST", default="redis")}:6379/0'  # noqa: F821
    CACHES['default']['LOCATION'] = REDIS_URL  # noqa: F821
    CELERY_BROKER_URL = REDIS_URL  # noqa: F821
    CELERY_RESULT_BACKEND = REDIS_URL  # noqa: F821

CORS_ALLOW_ALL_ORIGINS = False

SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] = [  # noqa: F821
    'rest_framework.permissions.IsAdminUser',
]
