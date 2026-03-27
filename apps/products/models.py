import uuid as uuid_lib

from django.db import models
from django.conf import settings

from apps.common.models import TimeStampedModel


class Photo(TimeStampedModel):
    """
    Универсальная галерея фотографий.
    Хранит оригинал + thumbnail + medium.
    """
    name = models.CharField(max_length=255, verbose_name='Название фотографии')
    image = models.ImageField(
        upload_to='photos/original/',
        null=True, blank=True,
        verbose_name='Изображение',
    )
    thumbnail_image = models.ImageField(
        upload_to='photos/thumb/',
        null=True, blank=True,
        verbose_name='Миниатюра',
    )
    medium_image = models.ImageField(
        upload_to='photos/medium/',
        null=True, blank=True,
        verbose_name='Среднее изображение',
    )
    alt_text = models.CharField(
        max_length=255, null=True, blank=True, verbose_name='Альтернативный текст'
    )
    description = models.TextField(null=True, blank=True, verbose_name='Описание')
    is_public = models.BooleanField(default=True, verbose_name='Опубликовано')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_photos',
        verbose_name='Загрузил',
    )

    class Meta:
        verbose_name = 'Фотография'
        verbose_name_plural = 'Фотографии'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Category(TimeStampedModel):
    """Категория продуктов. Поддерживает вложенность (parent)."""

    uuid = models.UUIDField(
        default=uuid_lib.uuid4,
        editable=False,
        unique=True,
        verbose_name='UUID',
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name='Создатель категории',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительская категория',
    )
    name = models.CharField(max_length=255, verbose_name='Название категории')
    order = models.PositiveBigIntegerField(
        null=True, blank=True, verbose_name='Порядок сортировки'
    )
    is_hidden = models.BooleanField(default=False, verbose_name='Скрытое')
    image = models.ImageField(
        upload_to='categories/images/',
        null=True, blank=True,
        verbose_name='Изображение',
    )
    icon = models.ImageField(
        upload_to='categories/icons/',
        null=True, blank=True,
        verbose_name='Иконка',
    )

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    """Продукт магазина."""

    uuid = models.UUIDField(
        default=uuid_lib.uuid4,
        unique=True,
        verbose_name='UUID',
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name='Магазин',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        verbose_name='Категория',
    )
    article = models.CharField(
        max_length=255, null=True, blank=True, verbose_name='Артикул',
        db_column='acrticul',
    )
    name = models.CharField(max_length=255, verbose_name='Название продукта')
    short_description = models.CharField(
        max_length=255, verbose_name='Краткое описание'
    )
    description = models.TextField(null=True, blank=True, verbose_name='Полное описание')
    is_for_children = models.BooleanField(default=False, verbose_name='Для детей')
    is_vegan = models.BooleanField(default=False, verbose_name='Веган')
    is_popular = models.BooleanField(default=False, verbose_name='Популярное')
    is_hidden = models.BooleanField(default=False, verbose_name='Скрытое')
    is_stop = models.BooleanField(default=False, verbose_name='Остановленное')
    viewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='viewed_products',
        verbose_name='Просмотры',
    )

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'is_hidden'], name='product_store_hidden_idx'),
        ]

    def __str__(self):
        return self.name

    # NOTE: viewers_count is intentionally NOT a property here.
    # It is provided as a DB-level annotation (Count('viewers', distinct=True))
    # in _product_qs_with_fav() for efficient bulk access without N+1 queries.
    # Accessing product.viewers_count on an annotated queryset object is free.
    # If you need the count outside that queryset, call:
    #   product.viewers.count()


class ProductModel(TimeStampedModel):
    """Вариант (модель) продукта — цена, количество, фото."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='models',
        verbose_name='Продукт',
    )
    name = models.CharField(max_length=255, verbose_name='Модель')
    quantity = models.PositiveBigIntegerField(default=0, verbose_name='Количество')
    price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name='Цена'
    )

    class Meta:
        verbose_name = 'Модель продукта'
        verbose_name_plural = 'Модели продуктов'
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name='productmodel_quantity_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name='productmodel_price_non_negative'
            ),
        ]

    def __str__(self):
        return f'{self.product.name} — {self.name}'


class ProductPhoto(TimeStampedModel):
    """Фото привязанное к модели (варианту) продукта."""

    product = models.ForeignKey(
        ProductModel,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name='Модель продукта',
    )
    image = models.ForeignKey(
        Photo,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='product_photos',
        verbose_name='Изображение',
    )

    class Meta:
        verbose_name = 'Изображение продукта'
        verbose_name_plural = 'Изображения продуктов'

    def __str__(self):
        return f'Фото модели {self.product}'


class FavoriteProduct(TimeStampedModel):
    """Избранные продукты пользователя."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
        verbose_name='Пользователь',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='favorited_by',
        verbose_name='Продукт',
    )

    class Meta:
        verbose_name = 'Избранный продукт'
        verbose_name_plural = 'Избранные продукты'
        unique_together = ('user', 'product')

    def __str__(self):
        return f'{self.user} → {self.product}'
