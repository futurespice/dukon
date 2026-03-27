import uuid
from django.db import models
from apps.common.models import TimeStampedModel


class Employee(TimeStampedModel):

    class Position(models.TextChoices):
        WAITER = 'WAITER', 'Официант'
        ACCOUNTANT = 'ACCOUNTANT', 'Бухгалтер'
        CASHIER = 'CASHIER', 'Кассир'

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='employees',
        verbose_name='Магазин',
    )
    username = models.CharField(max_length=255, unique=True, verbose_name='Логин сотрудника')
    password = models.CharField(
        max_length=255, null=True, blank=True,
        verbose_name='Пароль сотрудника',
        help_text='Хранится в виде хеша Django',
    )
    first_name = models.CharField(max_length=255, verbose_name='Имя сотрудника')
    last_name = models.CharField(max_length=255, null=True, blank=True, verbose_name='Фамилия сотрудника')
    position = models.CharField(
        max_length=20, choices=Position.choices,
        verbose_name='Должность сотрудника',
    )
    token = models.UUIDField(
        default=uuid.uuid4, editable=False,
        verbose_name='Токен сессии',
    )
    # AUDIT-3 FIX #7: Track when the token was issued so we can enforce a TTL.
    token_created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Токен выдан',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активность сотрудника')

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['first_name']

    def __str__(self):
        return f'{self.first_name} ({self.store.name})'

    def refresh_token(self):
        from django.utils import timezone
        self.token = uuid.uuid4()
        self.token_created_at = timezone.now()
        self.save(update_fields=['token', 'token_created_at'])

    def is_token_valid(self, max_age_hours: int = 24) -> bool:
        """Check if the token is still within its TTL."""
        from django.utils import timezone
        from datetime import timedelta
        from django.conf import settings
        max_hours = getattr(settings, 'EMPLOYEE_TOKEN_TTL_HOURS', max_age_hours)
        if self.token_created_at is None:
            return False
        return timezone.now() - self.token_created_at < timedelta(hours=max_hours)
