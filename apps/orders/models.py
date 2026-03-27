from decimal import Decimal

from django.db import models
from django.conf import settings

from apps.common.models import TimeStampedModel


class Order(TimeStampedModel):

    class PaymentType(models.TextChoices):
        MBANK = 'MBANK', 'MBank'
        ONLINE_PAY = 'ONLINE_PAY', 'Онлайн оплата'
        IN_CASH = 'IN_CASH', 'Наличные'

    class DeliveryType(models.TextChoices):
        SELF_PICKUP = 'SELF_PICKUP', 'Самовывоз'
        DELIVERY = 'DELIVERY', 'Доставка'

    class OrderStatus(models.TextChoices):
        IN_PROCESSING = 'IN_PROCESSING', 'В обработке'
        ACCEPTED = 'ACCEPTED', 'Принят'
        CANCELED = 'CANCELED', 'Отменён'
        REJECTED = 'REJECTED', 'Отклонён'

    class DeliveryStatus(models.TextChoices):
        IN_PROCESSING = 'IN_PROCESSING', 'В обработке'
        IN_PROGRESS = 'IN_PROGRESS', 'В пути'
        DELIVERED = 'DELIVERED', 'Доставлен'
        CANCELED = 'CANCELED', 'Отменён'
        RETURNED = 'RETURNED', 'Возврат'
        REJECTED = 'REJECTED', 'Отклонён'

    class PaymentStatus(models.TextChoices):
        WAITING_FOR_PAY = 'WAITING_FOR_PAY', 'Ожидает оплаты'
        PAID = 'PAID', 'Оплачен'
        REFUNDED = 'REFUNDED', 'Возврат'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='orders',
        verbose_name='Пользователь',
    )
    phone_number = models.CharField(max_length=128, verbose_name='Номер телефона')
    first_name = models.CharField(max_length=250, verbose_name='Имя пользователя')
    last_name = models.CharField(max_length=250, null=True, blank=True, verbose_name='Фамилия пользователя')
    comment = models.CharField(max_length=500, null=True, blank=True, verbose_name='Комментарий')
    address = models.CharField(max_length=250, verbose_name='Адрес доставки')
    payment_type = models.CharField(
        max_length=20, choices=PaymentType.choices,
        default=PaymentType.IN_CASH, verbose_name='Тип оплаты',
    )
    delivery_type = models.CharField(
        max_length=20, choices=DeliveryType.choices,
        default=DeliveryType.SELF_PICKUP, verbose_name='Тип доставки',
    )
    order_status = models.CharField(
        max_length=20, choices=OrderStatus.choices,
        default=OrderStatus.IN_PROCESSING, verbose_name='Статус заказа',
    )
    delivery_status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices,
        default=DeliveryStatus.IN_PROCESSING, verbose_name='Статус доставки',
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices,
        default=PaymentStatus.WAITING_FOR_PAY, verbose_name='Статус оплаты',
    )
    check_photo = models.ImageField(
        upload_to='orders/checks/', null=True, blank=True,
        verbose_name='Фото чека',
    )
    notifications_sent = models.BooleanField(
        default=False, verbose_name='Уведомления отправлены',
        db_column='sended_notifications',
    )
    idempotency_key = models.CharField(
        max_length=255, null=True, blank=True, unique=True,
        verbose_name='Ключ идемпотентности'
    )

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f'Заказ #{self.pk} — {self.first_name}'

    @property
    def total_price(self) -> Decimal:
        """
        Сумма заказа по зафиксированным ценам на момент создания.

        R-5 FIX (N+1 outside API prefetch context):
        `self.items.all()` uses Django’s prefetch cache when the object
        was fetched via a queryset that includes prefetch_related('items')
        (as all API views do via _ORDER_QS).  However, callers outside that
        context — Celery tasks, Django admin, management commands, tests —
        would issue one SELECT per Order instance.

        Fix: use prefetch_related_objects() to populate the cache on-demand
        when 'items' are not already prefetched.  The cost is one SELECT for
        the batch of items (not per-order), and it is a no-op when the cache
        is already populated by the calling queryset.
        """
        from django.db.models import prefetch_related_objects

        # Check Django's internal prefetch cache without triggering a query.
        # _prefetched_objects_cache is set by prefetch_related() machinery;
        # its absence means the object was fetched without prefetch context.
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'items' not in cache:
            # Auto-populate the prefetch cache with a single query.
            # After this call, self.items.all() reads from cache — no DB hit.
            prefetch_related_objects([self], 'items')

        return sum(
            (item.price_at_order * item.quantity for item in self.items.all()),
            Decimal('0'),
        )


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE,
        related_name='items', verbose_name='Заказ',
    )
    product = models.ForeignKey(
        'products.ProductModel',
        on_delete=models.SET_NULL,   # SET_NULL so history survives product deletion
        null=True,
        related_name='order_items',
        verbose_name='Продукт',
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name='Количество',
    )
    # Snapshot fields — зафиксированы в момент создания заказа
    price_at_order = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Цена на момент заказа',
        help_text='Фиксируется автоматически из ProductModel.price при создании заказа.',
    )
    product_name_at_order = models.CharField(
        max_length=512,
        verbose_name='Название продукта на момент заказа',
        help_text='Фиксируется автоматически для сохранения истории.',
    )

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name='orderitem_quantity_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(price_at_order__gte=0),
                name='orderitem_price_at_order_non_negative'
            ),
        ]

    def __str__(self):
        return f'{self.order} × {self.product_name_at_order} ({self.quantity} × {self.price_at_order})'

    @property
    def subtotal(self):
        return self.price_at_order * self.quantity
