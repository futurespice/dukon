"""
Per-app Swagger / Redoc views.

Each app gets its own:
  - schema endpoint  → /api/schema/{app}/
  - Swagger UI       → /swagger/{app}/
  - Redoc UI         → /redoc/{app}/

Plus a global "all endpoints" schema at the root.
"""
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# ---------------------------------------------------------------------------
# Preprocessing hook factories
# Hooks receive the full endpoint list and return a filtered subset.
# drf-spectacular calls them as callables, so no string-path needed.
# ---------------------------------------------------------------------------

def _make_prefix_filter(*prefixes):
    """Return a preprocessing hook that keeps only endpoints matching any prefix."""
    def hook(endpoints, **kwargs):
        return [
            (path, path_regex, method, callback)
            for path, path_regex, method, callback in endpoints
            if any(prefix in path for prefix in prefixes)
        ]
    return hook


# ---------------------------------------------------------------------------
# Per-app filter hooks (must be importable top-level callables)
# ---------------------------------------------------------------------------

filter_accounts = _make_prefix_filter('/accounts/')
filter_stores = _make_prefix_filter(
    '/stores/', '/store-photos/', '/banke-types/',
    '/balance-transactions/', '/tariff-plans-transactions/',
    '/balance/set/', '/slides/',
)
filter_products = _make_prefix_filter(
    '/products/', '/photos/', '/categories/',
    '/product-models/', '/product-photos/',
    '/favorites/', '/my-products/',
)
filter_orders = _make_prefix_filter('/orders/')
filter_employees = _make_prefix_filter('/employees/')
filter_notifications = _make_prefix_filter('/notifications/')
filter_countryapi = _make_prefix_filter('/countryapi/')


# ---------------------------------------------------------------------------
# Per-app schema views (SpectacularAPIView instances)
# ---------------------------------------------------------------------------

_COMMON_SETTINGS = {
    'SERVE_INCLUDE_SCHEMA': False,
}

AccountsSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Accounts API',
        'DESCRIPTION': 'Аутентификация, профиль, верификация, Google OAuth, 2FA.',
        'PREPROCESSING_HOOKS': [filter_accounts],
    }
)

StoresSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Stores API',
        'DESCRIPTION': 'Магазины, фото, банковские реквизиты, тарифы, баланс, слайды, промокоды.',
        'PREPROCESSING_HOOKS': [filter_stores],
    }
)

ProductsSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Products API',
        'DESCRIPTION': 'Продукты, категории, фото, модели, избранное, импорт/экспорт.',
        'PREPROCESSING_HOOKS': [filter_products],
    }
)

OrdersSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Orders API',
        'DESCRIPTION': 'Заказы, позиции заказов, история.',
        'PREPROCESSING_HOOKS': [filter_orders],
    }
)

EmployeesSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Employees API',
        'DESCRIPTION': 'Сотрудники магазина, аутентификация сотрудников.',
        'PREPROCESSING_HOOKS': [filter_employees],
    }
)

NotificationsSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Notifications API',
        'DESCRIPTION': 'Уведомления пользователей.',
        'PREPROCESSING_HOOKS': [filter_notifications],
    }
)

CountryapiSchemaView = SpectacularAPIView.as_view(
    custom_settings={
        **_COMMON_SETTINGS,
        'TITLE': 'Dukon — Geography API',
        'DESCRIPTION': 'Страны, регионы, города.',
        'PREPROCESSING_HOOKS': [filter_countryapi],
    }
)

# ---------------------------------------------------------------------------
# Helper: build (schema_path, swagger_path, redoc_path, url_names) per app
# ---------------------------------------------------------------------------

APP_DOCS = [
    ('accounts',      AccountsSchemaView),
    ('stores',        StoresSchemaView),
    ('products',      ProductsSchemaView),
    ('orders',        OrdersSchemaView),
    ('employees',     EmployeesSchemaView),
    ('notifications', NotificationsSchemaView),
    ('countryapi',    CountryapiSchemaView),
]


def build_doc_urlpatterns():
    """
    Returns a list of URL patterns for per-app schemas + Swagger + Redoc.
    Call this from config/urls.py.
    """
    from django.urls import path as dj_path
    patterns = []
    for app_name, schema_view in APP_DOCS:
        schema_name = f'schema-{app_name}'
        swagger_name = f'swagger-{app_name}'
        redoc_name = f'redoc-{app_name}'

        patterns += [
            dj_path(
                f'api/schema/{app_name}/',
                schema_view,
                name=schema_name,
            ),
            dj_path(
                f'swagger/{app_name}/',
                SpectacularSwaggerView.as_view(url_name=schema_name),
                name=swagger_name,
            ),
            dj_path(
                f'redoc/{app_name}/',
                SpectacularRedocView.as_view(url_name=schema_name),
                name=redoc_name,
            ),
        ]
    return patterns
