"""
Celery tasks for asynchronous message delivery via WhatsApp (GreenAPI).

All verification codes (registration, password reset, phone change, 2FA)
are delivered exclusively through WhatsApp.
Tasks are routed to the 'urgent' queue so they are never blocked behind
heavy background tasks in the default queue.

Production celery worker must listen on both queues:
  celery -A config worker -Q default,urgent --concurrency=4
"""
import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    name='accounts.cleanup_expired_codes',
    queue='default',
)
def cleanup_expired_codes_task() -> int:
    """
    Periodic task: delete VerificationCode rows that expired more than 7 days ago.
    Prevents unbounded table growth — every login/register/2FA creates a row.
    Schedule: daily via django_celery_beat PeriodicTask.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.accounts.models import VerificationCode

    cutoff = timezone.now() - timedelta(days=7)
    # Q-3 NOTE: we delete ALL expired codes (both is_used=True and is_used=False)
    # older than 7 days. Keeping only unused ones would leave is_used=True rows
    # growing without bound. 7-day grace period is sufficient for any audit
    # need; codes are short-lived (5 min TTL) so anything older than 7 days
    # has no operational value. If longer audit retention is required, move
    # these rows to a separate audit table before deletion.
    deleted, _ = VerificationCode.objects.filter(expires_at__lt=cutoff).delete()
    if deleted:
        logger.info('Cleaned up %d expired verification codes.', deleted)
    return deleted


@shared_task(
    bind=True,
    queue='urgent',
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name='accounts.send_whatsapp_code',
)
def send_whatsapp_code_task(self, phone: str, code: int) -> bool:
    """
    Асинхронная отправка кода верификации через WhatsApp (GreenAPI).
    Используется для: регистрации, сброса пароля, смены номера, 2FA.
    Роутится в очередь 'urgent'.
    Автоматически повторяется до 3 раз при ошибке (exponential backoff).
    """
    if settings.DEBUG:
        logger.info('[DEBUG] WhatsApp code for %s: %s', phone, code)
        return True

    instance_id = getattr(settings, 'GREENAPI_INSTANCE_ID', '')
    token = getattr(settings, 'GREENAPI_TOKEN', '')
    base_url = getattr(settings, 'GREENAPI_BASE_URL', 'https://api.green-api.com')

    if not instance_id or not token:
        # Raise instead of returning False so autoretry_for=(Exception,) kicks in
        # and Sentry gets an alert. A silent return False makes Celery mark the
        # task as SUCCESS while the user never receives their code.
        raise RuntimeError(
            'GreenAPI credentials not configured — '
            'GREENAPI_INSTANCE_ID and GREENAPI_TOKEN must be set in environment.'
        )

    url = f'{base_url}/waInstance{instance_id}/sendMessage/{token}'
    digits = ''.join(filter(str.isdigit, phone))
    chat_id = f'{digits}@c.us'
    message = f'Ваш код подтверждения Dukon: *{code}*\nКод действителен 5 минут.'

    timeout = getattr(settings, 'GREENAPI_REQUEST_TIMEOUT', 15)

    response = requests.post(
        url,
        json={'chatId': chat_id, 'message': message},
        timeout=timeout,
    )
    if response.status_code == 200:
        return True
    logger.error('GreenAPI error %s for %s: %s', response.status_code, phone, response.text)
    # Q-5 FIX: raise_for_status() always raises an exception for 4xx/5xx
    # responses, so the `return False` that followed it was unreachable dead
    # code. Removed to avoid misleading readers into thinking the task can
    # return False (it can't — non-200 responses always raise, which triggers
    # the autoretry_for=(Exception,) machinery above).
    response.raise_for_status()
