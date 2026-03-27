"""
Django settings for Dukon Online project.
"""
from datetime import timedelta
from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'django_filters',
    'corsheaders',
    'phonenumber_field',
    'django_celery_beat',
]

LOCAL_APPS = [
    'apps.common',
    'apps.accounts',
    'apps.countryapi',
    'apps.stores',
    'apps.products',
    'apps.orders',
    'apps.employees',
    'apps.notifications',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='dukon_db'),
        # AUDIT SECURITY FIX: DB_USER and DB_PASSWORD have NO defaults.
        # A missing variable now raises an ImproperlyConfigured / UndefinedValueError
        # at startup instead of silently connecting with the well-known
        # 'postgres'/'postgres' credentials. This prevents accidental exposure
        # in staging/production environments where .env may be absent or incomplete.
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
    }
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.PhoneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / Media
# ---------------------------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = None

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'apps.common.schema.TaggedAutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '200/day',
        'user': '2000/day',
        'whatsapp': '5/hour',
        'auth': '20/hour',
        'verify_code': '10/hour',
        # R-3 FIX: 5 attempts per (IP, order_id) per hour.
        # Lower than verify_code (10/h) because order track is public and
        # the throttle key already includes order_id, so legitimate users
        # are unlikely to hit this limit in normal usage.
        'order_track': '5/hour',
    },
}

# ---------------------------------------------------------------------------
# JWT  (access: 60 min, refresh: 30 days)
# ---------------------------------------------------------------------------

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS', default='http://localhost:3000'
).split(',')

# ---------------------------------------------------------------------------
# Redis / Cache
# ---------------------------------------------------------------------------

REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        # Q-4 FIX: KEY_PREFIX namespaces all Django cache keys in Redis.
        # Without a prefix, keys from different environments (staging, prod)
        # sharing the same Redis instance collide silently.
        # Example: '2fa_pending:<uuid>' from staging overwrites the same key
        # in production. The prefix makes each environment's keys distinct:
        # production  → 'dukon:prod:2fa_pending:<uuid>'
        # staging     → 'dukon:staging:2fa_pending:<uuid>'
        # Override per environment in local.py / production.py as needed.
        'KEY_PREFIX': 'dukon',
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

# ---------------------------------------------------------------------------
# GreenAPI (WhatsApp) — единственный канал доставки кодов верификации
# ---------------------------------------------------------------------------

GREENAPI_INSTANCE_ID = config('GREENAPI_INSTANCE_ID', default='')
GREENAPI_TOKEN = config('GREENAPI_TOKEN', default='')
GREENAPI_BASE_URL = config(
    'GREENAPI_BASE_URL',
    default='https://api.green-api.com',
)
GREENAPI_REQUEST_TIMEOUT = config('GREENAPI_REQUEST_TIMEOUT', default=15, cast=int)

# ---------------------------------------------------------------------------
# Verification / 2FA TTL
# ---------------------------------------------------------------------------

VERIFY_CODE_TTL = 300  # 5 min
TWO_FA_TTL = 300       # 5 min

# ---------------------------------------------------------------------------
# Phone number field
# ---------------------------------------------------------------------------

# International platform — no default region.
# Users must always supply a full E.164 number including country code (e.g. +996555123456).
PHONENUMBER_DEFAULT_REGION = None

# ---------------------------------------------------------------------------
# Avatar upload limits
# ---------------------------------------------------------------------------

AVATAR_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------

SENTRY_DSN = config('SENTRY_DSN', default='')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=config('SENTRY_TRACES_RATE', default=0.1, cast=float),
        send_default_pii=False,
        environment=config('SENTRY_ENVIRONMENT', default='production'),
    )

# ---------------------------------------------------------------------------
# drf-spectacular
# ---------------------------------------------------------------------------

SPECTACULAR_SETTINGS = {
    'TITLE': 'Dukon Online API',
    'DESCRIPTION': 'Dukon Online — Backend API',
    'VERSION': 'v1',
    'SERVE_INCLUDE_SCHEMA': False,
    'CONTACT': {'email': 'office@prolabagency.com'},
    'LICENSE': {'name': 'BSD License'},
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],
    'TAGS': [
        {'name': 'Accounts',       'description': 'Регистрация, аутентификация, профиль, 2FA'},
        {'name': 'Stores',         'description': 'Магазины, слайды, фото, реквизиты, баланс'},
        {'name': 'Products',       'description': 'Продукты, категории, фотогалерея, избранное'},
        {'name': 'Orders',         'description': 'Заказы и позиции заказов'},
        {'name': 'Employees',      'description': 'Сотрудники магазинов'},
        {'name': 'Notifications',  'description': 'Уведомления пользователей'},
        {'name': 'CountryAPI',     'description': 'Страны, регионы, города'},
    ],
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': False,
}
