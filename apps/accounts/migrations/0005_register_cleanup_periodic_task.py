"""
Data migration: register cleanup_expired_codes_task as a daily PeriodicTask
in django_celery_beat so expired VerificationCode rows are pruned automatically.

Runs at 03:00 UTC every day — low-traffic window.
Safe to re-run: uses get_or_create so it never duplicates the task.
"""
from django.db import migrations


def register_periodic_task(apps, schema_editor):
    try:
        IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
        PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    except LookupError:
        # django_celery_beat is not installed or not migrated yet — skip silently.
        # The task can be registered manually via django-admin.
        return

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=1,
        period=IntervalSchedule.DAYS,
    )

    PeriodicTask.objects.get_or_create(
        name='cleanup_expired_verification_codes',
        defaults={
            'task': 'accounts.cleanup_expired_codes',
            'interval': schedule,
            'description': (
                'Deletes VerificationCode rows that expired more than 7 days ago. '
                'Prevents unbounded table growth from login/register/2FA/reset flows.'
            ),
        },
    )


def deregister_periodic_task(apps, schema_editor):
    try:
        PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    except LookupError:
        return
    PeriodicTask.objects.filter(name='cleanup_expired_verification_codes').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_user_is_2fa_enabled'),
    ]

    operations = [
        migrations.RunPython(
            register_periodic_task,
            reverse_code=deregister_periodic_task,
        ),
    ]
