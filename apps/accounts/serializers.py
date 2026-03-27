import logging

from django.contrib.auth import authenticate
from django.db import IntegrityError

from rest_framework import serializers

from apps.accounts.models import User, UserBonusCard
from apps.common.validators import validate_image_upload

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared phone validator
# ---------------------------------------------------------------------------

def _normalize_phone_field(value: str) -> str:
    """Normalise a phone to E.164. Raises ValidationError on invalid input."""
    from apps.accounts.services import normalize_phone
    try:
        return normalize_phone(value)
    except ValueError as exc:
        raise serializers.ValidationError(str(exc)) from exc


# ---------------------------------------------------------------------------
# UserBonusCard
# ---------------------------------------------------------------------------

class UserBonusCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBonusCard
        fields = ('id', 'bonus_card_number', 'created_at', 'updated_at')
        read_only_fields = ('id', 'bonus_card_number', 'created_at', 'updated_at')


# ---------------------------------------------------------------------------
# User / Profile
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    get_full_name = serializers.SerializerMethodField()
    image = serializers.ImageField(read_only=True)
    email = serializers.EmailField(read_only=True)
    bonus_card = UserBonusCardSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'first_name', 'last_name', 'middle_name', 'get_full_name',
            'image', 'role', 'is_active', 'last_login', 'last_activity',
            'date_joined', 'gender', 'date_of_birth', 'phone', 'email',
            'is_2fa_enabled', 'bonus_card',
        )
        read_only_fields = (
            'id', 'role', 'is_active', 'last_login',
            'last_activity', 'date_joined', 'image', 'email', 'bonus_card',
            'phone',
            'is_2fa_enabled',
        )

    def get_full_name(self, obj):
        return obj.get_full_name()


class UserProfileImageSerializer(serializers.ModelSerializer):
    """
    Validates image format and size before saving.

    DRY FIX #6: inline validation logic replaced by shared validate_image_upload()
    from apps.common.validators. Previously this class duplicated identical
    MIME-type + size + PIL-integrity checks from stores/serializers.py.
    """

    class Meta:
        model = User
        fields = ('image',)

    def validate_image(self, value):
        if value is None:
            return value
        # Avatar limit: 5 MB, JPEG/PNG/WEBP only (same as store photos).
        return validate_image_upload(value, max_mb=5, field_label='avatar')


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class RegisterUserSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=128)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')

    def validate_phone(self, value):
        return _normalize_phone_field(value)

    def create(self, validated_data):
        from apps.accounts.services import create_bonus_card_for_user, create_verification_code
        idempotency_key = validated_data.pop('idempotency_key', None)
        try:
            user = User.objects.create_user(
                phone=validated_data['phone'],
                password=validated_data['password'],
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                role=User.Role.NOT_VERIFIED,
            )
        except IntegrityError:
            raise serializers.ValidationError(
                {'phone': 'Пользователь с таким номером уже существует.'}
            )
        create_bonus_card_for_user(user)
        create_verification_code(phone=user.phone, purpose='REGISTER', user=user, idempotency_key=idempotency_key)
        return user


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

class DefaultLoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate_phone(self, value):
        return _normalize_phone_field(value)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get('request'),
            phone=attrs.get('phone'),
            password=attrs.get('password'),
        )
        if not user:
            raise serializers.ValidationError('Неверный телефон или пароль.')
        if not user.is_active:
            raise serializers.ValidationError('Аккаунт деактивирован.')
        if user.role == User.Role.NOT_VERIFIED:
            raise serializers.ValidationError({
                'detail': 'Номер телефона не подтверждён. Проверьте WhatsApp — там ваш код подтверждения.',
                'action_required': 'verify_phone',
                'resend_code_url': '/api/v1/accounts/resend-verify-code/',
            })
        attrs['user'] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Неверный текущий пароль.')
        return value


# ---------------------------------------------------------------------------
# Phone number change
# ---------------------------------------------------------------------------

class PhoneNumberChangeSerializer(serializers.Serializer):
    new_phone = serializers.CharField(max_length=128)

    def validate_new_phone(self, value):
        normalised = _normalize_phone_field(value)
        if User.objects.filter(phone=normalised).exists():
            raise serializers.ValidationError('Этот номер уже используется.')
        return normalised


# ---------------------------------------------------------------------------
# Reset password via WhatsApp
# ---------------------------------------------------------------------------

class ResendVerifyCodeSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=128)

    def validate_phone(self, value):
        return _normalize_phone_field(value)


class ResetPasswordSendCodeSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=128)

    def validate_phone(self, value):
        return _normalize_phone_field(value)


class ResetPasswordConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=128)
    code = serializers.IntegerField(min_value=1000, max_value=9999)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_phone(self, value):
        return _normalize_phone_field(value)


# ---------------------------------------------------------------------------
# 2FA (Two-Factor Authentication via WhatsApp)
# ---------------------------------------------------------------------------

class TwoFAConfirmSerializer(serializers.Serializer):
    two_fa_token = serializers.CharField()
    code = serializers.IntegerField(min_value=1000, max_value=9999)


# ---------------------------------------------------------------------------
# Phone verification (registration confirm, phone-change confirm)
# ---------------------------------------------------------------------------

class CheckVerifyCodeSerializer(serializers.Serializer):
    """Validate phone number and 4-digit confirmation code."""
    phone = serializers.CharField(max_length=128)
    code = serializers.IntegerField(min_value=1000, max_value=9999)

    def validate_phone(self, value):
        return _normalize_phone_field(value)


class PhoneChangeConfirmSerializer(serializers.Serializer):
    """Confirm phone change: just the 4-digit code (new phone is looked up from DB)."""
    code = serializers.IntegerField(min_value=1000, max_value=9999)
