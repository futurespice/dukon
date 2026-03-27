"""
Shared mixins and helper utilities used across multiple apps.
"""
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.common.constants import MAX_BULK_OPERATIONS


# ---------------------------------------------------------------------------
# Bulk-operation validation
# ---------------------------------------------------------------------------

def validate_bulk_ids(data, max_count: int = MAX_BULK_OPERATIONS, action: str = 'удалить'):
    """
    Validate the 'ids' field from request.data for bulk operations.

    Returns (ids, error_response):
      - On success: (list_of_ids, None)
      - On failure: (None, Response)

    Usage::

        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        MyModel.objects.filter(pk__in=ids, ...).delete()
    """
    ids = data.get('ids', [])
    if not isinstance(ids, list):
        return None, Response(
            {'detail': 'Поле ids должно быть массивом.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not ids:
        return None, Response(
            {'detail': 'Список ids пуст.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(ids) > max_count:
        return None, Response(
            {'detail': f'Нельзя {action} более {max_count} записей за один запрос.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # M-2 FIX: validate that every element is a plain integer.
    # Without this check, payloads like {"ids": ["abc", null, 1.5, true]}
    # pass the list check above and reach ORM .filter(pk__in=ids) where
    # PostgreSQL raises DataError (invalid input for integer) → unhandled 500.
    # bool is a subclass of int in Python, so we explicitly exclude it.
    invalid = [
        i for i, v in enumerate(ids)
        if not isinstance(v, int) or isinstance(v, bool)
    ]
    if invalid:
        return None, Response(
            {
                'detail': 'Все элементы ids должны быть целыми числами.',
                'invalid_indices': invalid,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return ids, None


# ---------------------------------------------------------------------------
# Serializer mixins
# ---------------------------------------------------------------------------

class PhoneNormalizeMixin:
    """
    DRF serializer mixin that normalises phone_number to E.164 via
    apps.accounts.services.normalize_phone.

    Include before ModelSerializer in the MRO::

        class MySerializer(PhoneNormalizeMixin, serializers.ModelSerializer):
            ...
    """

    def validate_phone_number(self, value):
        from apps.accounts.services import normalize_phone
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
