import os

from celery import Celery
from celery.schedules import crontab

# DEVOPS FIX #11: was defaulting to 'config.settings.production'.
# Running 'celery -A config worker' locally without Docker would load
# production settings, connect to the wrong DB/Redis, and fail silently
# or (worse) mutate production data.
# Correct default is 'local'; production deployments always set
# DJANGO_SETTINGS_MODULE explicitly via docker-compose environment:.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

app = Celery('dukon')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Periodic task schedule
#
# FIX #8: cleanup_expired_codes_task was declared in accounts/tasks.py but
# never registered with a schedule, meaning the VerificationCode table grew
# without bound (every login/registration/2FA creates a row).
#
# This beat_schedule runs the cleanup daily at 03:00 UTC — low-traffic window.
#
# Production celery beat worker command:
#   celery -A config beat --scheduler django_celery_beat.schedulers:DatabaseScheduler
# OR (simpler, no DB scheduler):
#   celery -A config beat -l info
# ---------------------------------------------------------------------------

app.conf.beat_schedule = {
    'cleanup-expired-verification-codes': {
        'task': 'accounts.cleanup_expired_codes',
        'schedule': crontab(hour=3, minute=0),
        'options': {'queue': 'default'},
    },
}
