from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model with created_at / updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        abstract = True
