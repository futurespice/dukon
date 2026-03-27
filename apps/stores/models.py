import uuid

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.conf import settings

from apps.common.models import TimeStampedModel


class BankType(TimeStampedModel):
    """Тип банка (справочник)."""

    name = models.CharField(max_length=255, unique=True, verbose_name='Название банка')

    class Meta:
        verbose_name = 'Тип банка'
        verbose_name_plural = 'Типы банков'
        ordering = ['name']
        db_table = 'stores_banketype'

    def __str__(self):
        return self.name


BankeType = BankType


class Store(TimeStampedModel):
    """
    Магазин.
    PK — UUID. Slug — уникальный человекочитаемый идентификатор.
    """

    class Theme(models.TextChoices):
        T1 = '1', 'Тема 1'
        T2 = '2', 'Тема 2'
        T3 = '3', 'Тема 3'
        T4 = '4', 'Тема 4'
        T5 = '5', 'Тема 5'
        T6 = '6', 'Тема 6'
        T7 = '7', 'Тема 7'
        T8 = '8', 'Тема 8'
        T9 = '9', 'Тема 9'
        T10 = '10', 'Тема 10'
        T11 = '11', 'Тема 11'
        T12 = '12', 'Тема 12'

    class TariffPlan(models.TextChoices):
        FREE = '0', 'Бесплатный'
        BASIC = '1', 'Базовый'
        STANDARD = '2', 'Стандарт'
        PREMIUM = '3', 'Премиум'

    class BonusSystemType(models.TextChoices):
        CASHBACK = '1', 'Кэшбэк'
        POINTS = '2', 'Баллы'

    class CashbackPercent(models.IntegerChoices):
        P1 = 1, '1%'
        P2 = 2, '2%'
        P3 = 3, '3%'
        P4 = 4, '4%'
        P5 = 5, '5%'
        P6 = 6, '6%'
        P7 = 7, '7%'
        P8 = 8, '8%'
        P9 = 9, '9%'
        P10 = 10, '10%'

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='UUID',
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Слаг магазина',
    )
    name = models.CharField(max_length=255, verbose_name='Название магазина')
    address = models.CharField(max_length=255, verbose_name='Адрес магазина')
    logo = models.ImageField(
        upload_to='stores/logos/',
        null=True, blank=True,
        verbose_name='Логотип',
    )
    phone_number = models.CharField(
        max_length=128, null=True, blank=True, verbose_name='Номер телефона'
    )
    description = models.TextField(null=True, blank=True, verbose_name='Описание магазина')
    theme = models.CharField(
        max_length=2,
        choices=Theme.choices,
        null=True, blank=True,
        verbose_name='Тема магазина',
    )

    # Social links
    url_2gis = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на 2GIS')
    url_goog_map = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на Google Maps')
    instagram_url = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на Instagram')
    facebook_url = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на Facebook')
    telegram_url = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на Telegram')
    youtube_url = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на YouTube')
    whatsapp_url = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на WhatsApp')
    tiktok_url = models.URLField(max_length=200, null=True, blank=True, verbose_name='URL на TikTok')

    cashback_percent = models.PositiveSmallIntegerField(
        choices=CashbackPercent.choices,
        default=CashbackPercent.P1,
        verbose_name='Процент кэшбэка',
    )
    tariff_plan = models.CharField(
        max_length=1,
        choices=TariffPlan.choices,
        default=TariffPlan.FREE,
        verbose_name='Тарифный план',
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name='Баланс',
    )
    type_of_bonus_system = models.CharField(
        max_length=1,
        choices=BonusSystemType.choices,
        default=BonusSystemType.CASHBACK,
        verbose_name='Тип системы начисления бонусов',
    )
    google_token = models.CharField(
        max_length=20, null=True, blank=True, verbose_name='Токен Google Аналитик'
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True, blank=True,
        verbose_name='Широта',
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True, blank=True,
        verbose_name='Долгота',
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_stores',
        verbose_name='Администратор',
    )
    region = models.ForeignKey(
        'countryapi.City',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stores',
        verbose_name='Город',
    )

    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'
        ordering = ['-created_at']
        constraints = [
            # M-4 FIX: enforce non-negative balance at the DB level.
            # purchase_tariff() already guards against going negative in code,
            # but a direct admin edit, raw SQL, or any future code path that
            # bypasses the service layer would silently produce negative values
            # without this constraint.
            models.CheckConstraint(
                condition=models.Q(balance__gte=0),
                name='store_balance_non_negative',
            ),
        ]

    def __str__(self):
        return self.name


class StorePhoto(TimeStampedModel):
    """Фотографии магазина."""

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name='Магазин',
    )
    photo = models.ImageField(
        upload_to='stores/photos/',
        null=True, blank=True,
        verbose_name='Фотография',
    )

    class Meta:
        verbose_name = 'Фото магазина'
        verbose_name_plural = 'Фото магазинов'

    def __str__(self):
        return f'Фото магазина {self.store.name}'


class StoreBankDetail(TimeStampedModel):
    """Банковские реквизиты магазина."""

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='bank_details',
        verbose_name='Магазин',
    )
    bank = models.ForeignKey(
        BankType,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bank_details',
        verbose_name='Тип банка',
    )
    bank_account_number = models.CharField(
        max_length=255, verbose_name='Номер счёта'
    )
    bank_account_holder_name = models.CharField(
        max_length=255, null=True, blank=True, verbose_name='Имя владельца счёта'
    )
    bank_account_holder_inn = models.CharField(
        max_length=255, null=True, blank=True, verbose_name='ИНН владельца счёта'
    )

    class Meta:
        verbose_name = 'Банковские реквизиты'
        verbose_name_plural = 'Банковские реквизиты'

    def __str__(self):
        return f'{self.store.name} — {self.bank_account_number}'


class StoreBalanceTransaction(TimeStampedModel):
    """Транзакция баланса магазина."""

    class TransactionType(models.TextChoices):
        INCOME = 'INCOME', 'Пополнение'
        OUTCOME = 'OUTCOME', 'Списание'

    class PaymentType(models.TextChoices):
        BUY_TARIF = 'BUY_TARIF', 'Покупка тарифа'
        BUY_EMPLOYEE = 'BUY_EMPLOYEE', 'Покупка сотрудника'
        CONT_TARIF = 'CONT_TARIF', 'Продление тарифа'
        CONT_EMPLOYEE = 'CONT_EMPLOYEE', 'Продление сотрудника'
        OTHER = 'OTHER', 'Прочее'

    idempotency_key = models.CharField(
        max_length=255, null=True, blank=True, unique=True,
        verbose_name='Ключ идемпотентности'
    )

    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Успешно'
        FAILURE = 'FAILURE', 'Ошибка'
        IN_PROCESSING = 'IN_PROCESSING', 'В обработке'

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='balance_transactions',
        verbose_name='Магазин',
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name='Сумма транзакции'
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
        verbose_name='Тип транзакции',
    )
    description = models.CharField(
        max_length=255, null=True, blank=True, verbose_name='Описание транзакции'
    )
    balance_before = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True, verbose_name='Баланс до транзакции'
    )
    balance_after = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True, verbose_name='Баланс после транзакции'
    )
    type = models.CharField(
        max_length=20,
        choices=PaymentType.choices,
        null=True, blank=True,
        verbose_name='Вид платежа',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROCESSING,
        verbose_name='Статус',
    )

    class Meta:
        verbose_name = 'Транзакция баланса магазина'
        verbose_name_plural = 'Транзакции баланса магазинов'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name='storebalancetransaction_amount_non_negative'
            ),
        ]

    def __str__(self):
        return f'{self.store.name} {self.transaction_type} {self.amount}'


class StoreTariffPlan(TimeStampedModel):
    """История тарифных планов магазина."""

    class TariffPlan(models.TextChoices):
        FREE = '0', 'Бесплатный'
        BASIC = '1', 'Базовый'
        STANDARD = '2', 'Стандарт'
        PREMIUM = '3', 'Премиум'

    class DurationType(models.TextChoices):
        MONTH_1 = '1', '1 месяц'
        MONTH_3 = '2', '3 месяца'
        MONTH_6 = '3', '6 месяцев'
        MONTH_12 = '4', '12 месяцев'

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='tariff_plans',
        verbose_name='Магазин',
    )
    tariff_plan = models.CharField(
        max_length=1,
        choices=TariffPlan.choices,
        verbose_name='Тарифный план',
    )
    start_date = models.DateTimeField(verbose_name='Дата начала действия тарифа')
    end_date = models.DateTimeField(
        null=True, blank=True, verbose_name='Дата окончания действия тарифа'
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name='Стоимость тарифа'
    )
    duration_type = models.CharField(
        max_length=1,
        choices=DurationType.choices,
        verbose_name='Тип длительности тарифа',
    )

    @property
    def is_active(self):
        from django.utils import timezone
        now = timezone.now()
        if self.end_date:
            return self.start_date <= now <= self.end_date
        return self.start_date <= now

    class Meta:
        verbose_name = 'Тарифный план магазина'
        verbose_name_plural = 'Тарифные планы магазинов'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name='storetariffplan_amount_non_negative'
            ),
        ]

    def __str__(self):
        return f'{self.store.name} — {self.get_tariff_plan_display()}'


class Slide(TimeStampedModel):
    """Слайды баннера магазина."""

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='slides',
        verbose_name='Магазин',
    )
    title = models.CharField(max_length=255, verbose_name='Заголовок')
    description = models.TextField(null=True, blank=True, verbose_name='Описание')
    button_text = models.CharField(max_length=100, verbose_name='Текст кнопки')
    button_web_url = models.URLField(
        max_length=255, null=True, blank=True, verbose_name='URL для веб-кнопки'
    )
    button_mob_url = models.URLField(
        max_length=255, null=True, blank=True, verbose_name='URL для мобильной версии'
    )
    image = models.ImageField(
        upload_to='stores/slides/',
        null=True, blank=True,
        verbose_name='Изображение',
    )
    # SMALL FIX #21: renamed from 'ordering' to 'sort_order' to avoid shadowing
    # Meta.ordering attribute name and confusing developers.
    # db_column='ordering' preserves the existing DB column — no data migration needed.
    sort_order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок',
        db_column='ordering',
    )

    class Meta:
        verbose_name = 'Слайд'
        verbose_name_plural = 'Слайды'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return f'{self.store.name} — {self.title}'


class Promocode(TimeStampedModel):
    """Промокоды для пополнения баланса магазина."""

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='promocodes',
        verbose_name='Магазин',
    )
    code = models.CharField(max_length=10, unique=True, verbose_name='Код')
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name='Сумма пополнения'
    )
    is_used = models.BooleanField(default=False, verbose_name='Использован')
    used_at = models.DateTimeField(null=True, blank=True, verbose_name='Когда использован')

    class Meta:
        verbose_name = 'Промокод'
        verbose_name_plural = 'Промокоды'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name='promocode_amount_non_negative'
            ),
        ]

    def __str__(self):
        return self.code
