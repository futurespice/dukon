"""
AUDIT-3 FIX #11 (Backend) / #8 (DevOps):
Management command to ensure the cleanup_expired_codes periodic task
is registered in django_celery_beat.

Run once after deploy or add to the migrate container:
    python manage.py setup_periodic_tasks
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Register periodic Celery tasks in django_celery_beat.'

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask, CrontabSchedule

        # Daily at 03:00 UTC — cleanup expired verification codes
        schedule, _ = CrontabSchedule.objects.get_or_create(
            hour='3',
            minute='0',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
        )

        task, created = PeriodicTask.objects.get_or_create(
            name='cleanup_expired_verification_codes',
            defaults={
                'task': 'accounts.cleanup_expired_codes',
                'crontab': schedule,
                'enabled': True,
                'description': 'Delete VerificationCode rows expired >7 days ago.',
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS(
                f'Created periodic task: {task.name}'
            ))
        else:
            # Ensure it uses the correct schedule even if it already exists
            if task.crontab_id != schedule.id:
                task.crontab = schedule
                task.save(update_fields=['crontab'])
                self.stdout.write(self.style.WARNING(
                    f'Updated schedule for: {task.name}'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'Periodic task already exists: {task.name}'
                ))
