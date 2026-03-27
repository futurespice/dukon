from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


def health_check(request):
    """
    DEVOPS FIX #13: lightweight health-check endpoint.

    Used by:
    - docker-compose healthcheck (web container)
    - nginx 'depends_on: web: condition: service_healthy'
    - CI smoke test after deployment
    - Load balancer / uptime monitoring

    Does NOT check DB or Redis — those have their own docker healthchecks.
    A simple 200 means gunicorn/Django started and can handle requests.
    """
    return JsonResponse({'status': 'ok'})


def deep_health_check(request):
    """
    DEVOPS FIX #13: deep health check that verifies DB + Redis connectivity.
    Returns 503 with details if any dependency is unreachable.
    """
    checks = {}
    all_ok = True

    # Check DB
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        checks['database'] = 'ok'
    except Exception as exc:
        checks['database'] = str(exc)
        all_ok = False

    # Check Redis / cache
    try:
        from django.core.cache import cache
        cache.set('_health_check', '1', timeout=5)
        val = cache.get('_health_check')
        checks['cache'] = 'ok' if val == '1' else 'unexpected value'
        if val != '1':
            all_ok = False
    except Exception as exc:
        checks['cache'] = str(exc)
        all_ok = False

    status_code = 200 if all_ok else 503
    return JsonResponse({'status': 'ok' if all_ok else 'degraded', **checks}, status=status_code)


api_v1 = [
    path('accounts/',      include('apps.accounts.urls')),
    path('countryapi/',    include('apps.countryapi.urls')),
    path('stores/',        include('apps.stores.urls')),
    path('products/',      include('apps.products.urls')),
    path('orders/',        include('apps.orders.urls')),
    path('employees/',     include('apps.employees.urls')),
    path('notifications/', include('apps.notifications.urls')),
]

urlpatterns = [
    # Health check — no auth, no throttle, no logging overhead
    path('health/', health_check, name='health-check'),
    path('health/deep/', deep_health_check, name='deep-health-check'),

    path('admin/', admin.site.urls),
    path('api/v1/', include(api_v1)),

    # Swagger / Redoc (protected by SPECTACULAR_SETTINGS.SERVE_PERMISSIONS)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
