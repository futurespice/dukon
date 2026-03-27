import logging

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.common.validators import validate_image_upload
from apps.stores.models import (
    Store, StorePhoto, StoreBankDetail, BankType,
    StoreBalanceTransaction, StoreTariffPlan, Slide, Promocode,
)

logger = logging.getLogger(__name__)

# DRY FIX #6: _validate_uploaded_image() has been replaced by the shared
# validate_image_upload() from apps.common.validators. The local copy has
# been deleted. Both stores and accounts now use the same implementation.


# ---------------------------------------------------------------------------
# BankType
# ---------------------------------------------------------------------------

class BankTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankType
        fields = ('id', 'name', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


BankeTypeSerializer = BankTypeSerializer


# ---------------------------------------------------------------------------
# StorePhoto
# ---------------------------------------------------------------------------

class StorePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorePhoto
        fields = ('id', 'photo')
        read_only_fields = ('id',)


class StorePhotoCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorePhoto
        fields = ('id', 'photo', 'store')
        read_only_fields = ('id',)

    def validate_photo(self, value):
        return validate_image_upload(value, field_label='store_photo')

    def validate_store(self, value):
        """Ensure the requesting user owns the store they're attaching a photo to."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.admin_user != request.user:
                raise PermissionDenied('Доступ разрешён только владельцу магазина.')
        return value


# ---------------------------------------------------------------------------
# Slide (nested inside Store)
# ---------------------------------------------------------------------------

class SlideNestedSerializer(serializers.ModelSerializer):
    """Lightweight serializer used when slides are embedded inside StoreSerializer."""
    class Meta:
        model = Slide
        fields = (
            'id', 'title', 'description', 'button_text',
            'button_web_url', 'button_mob_url', 'image', 'sort_order',
        )
        read_only_fields = ('id',)


# ---------------------------------------------------------------------------
# Store — PUBLIC (no sensitive financial data)
# ---------------------------------------------------------------------------

class StoreSerializer(serializers.ModelSerializer):
    """
    Public store serializer.
    - admin_user: read_only — never accepted from request body.
    - balance: excluded — must not be publicly visible.
    Use StoreOwnerSerializer for owner-facing endpoints.
    """
    photos = StorePhotoSerializer(many=True, read_only=True)
    slides = SlideNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Store
        fields = (
            'uuid', 'photos', 'slides', 'created_at', 'updated_at',
            'theme', 'slug', 'name', 'address', 'logo',
            'phone_number', 'description',
            'url_2gis', 'url_goog_map', 'instagram_url', 'facebook_url',
            'telegram_url', 'youtube_url', 'whatsapp_url', 'tiktok_url',
            'cashback_percent', 'tariff_plan',
            'type_of_bonus_system', 'google_token',
            'latitude', 'longitude',
            'region',
        )
        read_only_fields = ('uuid', 'created_at', 'updated_at', 'logo')


StoreListSerializer = StoreSerializer


# ---------------------------------------------------------------------------
# Store — OWNER (includes balance)
# ---------------------------------------------------------------------------

class StoreOwnerSerializer(StoreSerializer):
    """Extended serializer for store owner endpoints. Includes balance and admin_user."""
    class Meta(StoreSerializer.Meta):
        fields = StoreSerializer.Meta.fields + ('balance', 'admin_user')
        read_only_fields = StoreSerializer.Meta.read_only_fields + ('balance', 'admin_user')


# ---------------------------------------------------------------------------
# Slide (full CRUD)
# ---------------------------------------------------------------------------

class SlideSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slide
        fields = (
            'id', 'title', 'description', 'button_text',
            'button_web_url', 'button_mob_url', 'image',
            'store', 'sort_order',
        )
        read_only_fields = ('id', 'store')

    def validate_image(self, value):
        if value is None:
            return value
        return validate_image_upload(value, field_label='slide_image')

    def validate_sort_order(self, value):
        if value is not None and (value < 0 or value > 9999):
            raise serializers.ValidationError(
                'Значение sort_order должно быть от 0 до 9999.'
            )
        return value


# ---------------------------------------------------------------------------
# StoreBankDetail
# ---------------------------------------------------------------------------

class StoreBankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreBankDetail
        fields = (
            'id', 'created_at', 'updated_at',
            'bank_account_number', 'bank_account_holder_name',
            'bank_account_holder_inn', 'store', 'bank',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_store(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.admin_user != request.user:
                raise PermissionDenied('Доступ запрещён: вы не владелец этого магазина.')
        return value


class StoreBankDetailListSerializer(serializers.ModelSerializer):
    bank = BankTypeSerializer(read_only=True)

    class Meta:
        model = StoreBankDetail
        fields = (
            'id', 'bank', 'created_at', 'updated_at',
            'bank_account_number', 'bank_account_holder_name',
            'bank_account_holder_inn', 'store',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


# ---------------------------------------------------------------------------
# Lightweight store reference for use inside transaction/tariff lists.
# ---------------------------------------------------------------------------

class StoreShortSerializer(serializers.ModelSerializer):
    """Minimal store data for embedding inside transaction lists."""

    class Meta:
        model = Store
        fields = ('uuid', 'name', 'slug', 'tariff_plan', 'balance')
        read_only_fields = ('uuid', 'name', 'slug', 'tariff_plan', 'balance')


# ---------------------------------------------------------------------------
# StoreBalanceTransaction
# ---------------------------------------------------------------------------

class StoreBalanceTransactionListSerializer(serializers.ModelSerializer):
    store = StoreShortSerializer(read_only=True)

    class Meta:
        model = StoreBalanceTransaction
        fields = (
            'id', 'store', 'created_at', 'updated_at',
            'amount', 'transaction_type', 'description',
            'balance_before', 'balance_after',
            'type', 'status',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class StoreBalanceTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreBalanceTransaction
        fields = (
            'id', 'created_at', 'updated_at',
            'amount', 'transaction_type', 'description',
            'balance_before', 'balance_after',
            'type', 'status', 'store',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


# ---------------------------------------------------------------------------
# StoreTariffPlan
# ---------------------------------------------------------------------------

class StoreTariffPlanSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = StoreTariffPlan
        fields = (
            'id', 'created_at', 'updated_at',
            'tariff_plan', 'start_date', 'end_date',
            'amount', 'is_active', 'duration_type', 'store',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'is_active')


class StoreTariffPlanCreateSerializer(serializers.Serializer):
    tariff = serializers.ChoiceField(choices=StoreTariffPlan.TariffPlan.choices)
    store = serializers.UUIDField()
    duration_type = serializers.ChoiceField(choices=StoreTariffPlan.DurationType.choices)


# ---------------------------------------------------------------------------
# Promocode
# ---------------------------------------------------------------------------

class ToActivatePromocodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10, min_length=1)
    store = serializers.UUIDField(
        help_text='UUID магазина, которому принадлежит промокод. '
                  'Пользователь должен быть владельцем этого магазина.',
    )
