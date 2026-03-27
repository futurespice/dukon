from django.db import models
from apps.common.models import TimeStampedModel


class Country(TimeStampedModel):
    """Страна."""

    name = models.CharField(max_length=255, unique=True, verbose_name='Название страны')
    code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        verbose_name='Код страны (ISO)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'
        ordering = ['name']

    def __str__(self):
        return self.name


class Region(TimeStampedModel):
    """
    Область / штат / регион внутри страны.
    В схеме: ListRegion → filter by country.
    """

    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name='regions',
        verbose_name='Страна',
    )
    name = models.CharField(max_length=255, verbose_name='Название региона')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
        ordering = ['name']
        unique_together = ('country', 'name')

    def __str__(self):
        return f'{self.name} ({self.country})'


class City(TimeStampedModel):
    """
    Город внутри региона.
    В схеме: ListCity → filter by region.
    """

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='cities',
        verbose_name='Регион',
    )
    name = models.CharField(max_length=255, verbose_name='Название города')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        verbose_name = 'Город'
        verbose_name_plural = 'Города'
        ordering = ['name']
        unique_together = ('region', 'name')

    def __str__(self):
        return f'{self.name} ({self.region})'
