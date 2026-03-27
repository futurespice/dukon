import uuid

from django.core.cache import cache
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.accounts.models import User, VerificationCode
from apps.accounts.serializers import (
    RegisterUserSerializer,
    DefaultLoginSerializer,
    LogoutSerializer,
    ChangePasswordSerializer,
    PhoneNumberChangeSerializer,
    UserProfileSerializer,
    UserProfileImageSerializer,
    ResetPasswordSendCodeSerializer,
    ResetPasswordConfirmSerializer,
    ResendVerifyCodeSerializer,
    TwoFAConfirmSerializer,
    CheckVerifyCodeSerializer,
    PhoneChangeConfirmSerializer,
)
from apps.accounts.services import (
    get_tokens_for_user,
    blacklist_all_user_tokens,
    create_verification_code,
    validate_verification_code,
    normalize_phone,
)
from apps.accounts.throttles import AuthThrottle, VerifyCodeThrottle, WhatsAppThrottle

_SAFE_RESET_RESPONSE = {'detail': 'Если номер зарегистрирован, вы получите код в WhatsApp.'}

_2FA_CACHE_PREFIX = '2fa_pending:'
_2FA_ATTEMPTS_PREFIX = '2fa_attempts:'
_2FA_MAX_ATTEMPTS = 5
_2FA_TTL = getattr(settings, 'TWO_FA_TTL', 300)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_password(request):
    """
    Validate that the request contains a correct password for request.user.
    Returns None on success, or an error Response on failure.
    """
    password = request.data.get('password')
    if not password:
        return Response(
            {'detail': 'Поле password обязательно.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not request.user.check_password(password):
        return Response(
            {'detail': 'Неверный пароль.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


# ---------------------------------------------------------------------------
# POST /accounts/register/
# ---------------------------------------------------------------------------

class RegisterView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthThrottle, WhatsAppThrottle)

    def post(self, request):
        serializer = RegisterUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(idempotency_key=request.headers.get('Idempotency-Key'))
        return Response(
            {'detail': 'Регистрация прошла успешно. Введите код подтверждения из WhatsApp.'},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# POST /accounts/login/
# ---------------------------------------------------------------------------

class LoginView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthThrottle,)

    def post(self, request):
        serializer = DefaultLoginSerializer(data=request.data, context={'request': request})

        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                nfe = detail.get('non_field_errors')
                if isinstance(nfe, list) and len(nfe) == 1 and isinstance(nfe[0], dict):
                    inner = nfe[0]
                    if inner.get('action_required') == 'verify_phone':
                        return Response(inner, status=status.HTTP_400_BAD_REQUEST)
            raise

        user = serializer.validated_data['user']

        if user.is_2fa_enabled:
            two_fa_token = str(uuid.uuid4())
            cache.set(f'{_2FA_CACHE_PREFIX}{two_fa_token}', user.pk, timeout=_2FA_TTL)
            create_verification_code(
                phone=user.phone,
                purpose=VerificationCode.Purpose.TWO_FA,
                user=user,
                idempotency_key=request.headers.get('Idempotency-Key')
            )
            return Response(
                {
                    'detail': 'Код подтверждения отправлен в WhatsApp.',
                    '2fa_required': True,
                    'two_fa_token': two_fa_token,
                },
                status=status.HTTP_200_OK,
            )

        user.last_activity = timezone.now()
        user.save(update_fields=['last_activity'])
        return Response(get_tokens_for_user(user), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# POST /accounts/logout/
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            token.blacklist()
        except TokenError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Выход выполнен успешно.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# GET / PUT / PATCH / DELETE /accounts/profile/
# ---------------------------------------------------------------------------

class ProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    def _validate_phone_not_changed(self, request):
        incoming_phone = request.data.get('phone')
        if incoming_phone:
            try:
                normalised = normalize_phone(incoming_phone)
            except ValueError:
                raise DRFValidationError({'phone': 'Неверный формат номера телефона.'})
            if normalised != request.user.phone:
                raise DRFValidationError({
                    'phone': (
                        'Смена номера телефона через этот endpoint не поддерживается. '
                        'Используйте POST /api/v1/accounts/phone-number-change/'
                    )
                })

    def put(self, request):
        self._validate_phone_not_changed(request)
        serializer = UserProfileSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request):
        self._validate_phone_not_changed(request)
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        if err := _require_password(request):
            return err
        user = request.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        blacklist_all_user_tokens(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileImageView(APIView):
    """PATCH /accounts/profile/image/ — upload/replace avatar (multipart)."""
    permission_classes = (IsAuthenticated,)

    def patch(self, request):
        serializer = UserProfileImageSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserProfileSerializer(request.user).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# POST /accounts/change-password/
# ---------------------------------------------------------------------------

class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        blacklist_all_user_tokens(request.user)
        tokens = get_tokens_for_user(request.user)
        return Response(
            {'detail': 'Пароль успешно изменён.', **tokens},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# POST /accounts/reset-password/send-code/
# ---------------------------------------------------------------------------

class ResetPasswordSendCodeView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (WhatsAppThrottle,)

    def post(self, request):
        serializer = ResetPasswordSendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        try:
            user = User.objects.get(phone=phone, is_active=True)
            create_verification_code(
                phone=phone,
                purpose=VerificationCode.Purpose.RESET_PASSWORD,
                user=user,
                idempotency_key=request.headers.get('Idempotency-Key')
            )
        except User.DoesNotExist:
            pass
        return Response(_SAFE_RESET_RESPONSE, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# POST /accounts/reset-password/confirm/
# ---------------------------------------------------------------------------

class ResetPasswordConfirmView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (VerifyCodeThrottle,)

    def post(self, request):
        serializer = ResetPasswordConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = User.objects.get(phone=data['phone'])
        except User.DoesNotExist:
            return Response(
                {'detail': 'Неверный или просроченный код.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # wrap code validation + password update in one atomic block so that
        # if user.save() fails after the code is marked is_used=True the whole
        # operation rolls back and the code can be reused.
        #
        # Q-1 NOTE: `return Response(...)` inside `with transaction.atomic()`
        # does NOT trigger a rollback — Django only rolls back on unhandled
        # exceptions. A `return` exits the `with` block cleanly, causing the
        # transaction to COMMIT (the UPDATE that marked the code is_used stays).
        # This is intentional here: an invalid code marks nothing in the DB
        # (validate_verification_code returns False with 0 rows updated),
        # so there is nothing harmful to commit.
        with transaction.atomic():
            valid = validate_verification_code(
                phone=data['phone'],
                code=data['code'],
                purpose=VerificationCode.Purpose.RESET_PASSWORD,
            )
            if not valid:
                return Response(
                    {'detail': 'Неверный или просроченный код.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(data['new_password'])
            user.save(update_fields=['password'])

        blacklist_all_user_tokens(user)

        if user.role == User.Role.NOT_VERIFIED:
            return Response(
                {
                    'detail': 'Пароль успешно сброшен. Для входа подтвердите номер телефона.',
                    'action_required': 'verify_phone',
                },
                status=status.HTTP_200_OK,
            )

        tokens = get_tokens_for_user(user)
        return Response(
            {'detail': 'Пароль успешно сброшен.', **tokens},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# POST /accounts/check/verify-code/
# ---------------------------------------------------------------------------

class CheckVerifyCodeView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (VerifyCodeThrottle,)

    def post(self, request):
        serializer = CheckVerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']

        # R-2 FIX (Security — verification code consumed without effect):
        # Original flow: validate_verification_code() marks is_used=True,
        # THEN the try/except User.DoesNotExist catches a missing user and
        # returns 404 via `return` inside transaction.atomic().
        # `return` inside atomic() does NOT rollback — the transaction commits,
        # the code is permanently spent, but the user is never verified.
        # This means a deleted or phantom user can silently consume valid codes.
        #
        # Fix: look up the user BEFORE entering the transaction.  If the user
        # doesn't exist we fail cheaply before touching the VerificationCode
        # table, so no code is ever consumed for a non-existent user.
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response(
                {'detail': 'Пользователь не найден.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # wrap code validation + role update in one atomic block so that if
        # user.save() fails after the code is marked is_used=True the whole
        # operation rolls back and the code can be reused.
        #
        # Q-1 NOTE: `return` inside `with atomic()` commits, not rolls back.
        # Safe here because an invalid code leaves 0 DB rows changed.
        with transaction.atomic():
            valid = validate_verification_code(
                phone=phone,
                code=code,
                purpose=VerificationCode.Purpose.REGISTER,
            )
            if not valid:
                return Response(
                    {'detail': 'Неверный или просроченный код.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.role == User.Role.NOT_VERIFIED:
                user.role = User.Role.CLIENT
                user.save(update_fields=['role'])

        tokens = get_tokens_for_user(user)
        return Response({'detail': 'Номер подтверждён.', **tokens}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# POST /accounts/resend-verify-code/
# ---------------------------------------------------------------------------

class ResendVerifyCodeView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (WhatsAppThrottle,)

    def post(self, request):
        serializer = ResendVerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']

        try:
            user = User.objects.get(phone=phone, role=User.Role.NOT_VERIFIED)
            create_verification_code(
                phone=phone,
                purpose=VerificationCode.Purpose.REGISTER,
                user=user,
                idempotency_key=request.headers.get('Idempotency-Key')
            )
        except User.DoesNotExist:
            pass

        return Response(
            {'detail': 'Если номер зарегистрирован и не подтверждён, код будет выслан повторно в WhatsApp.'},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# POST /accounts/phone-number-change/
# POST /accounts/phone-number-change/confirm/
# ---------------------------------------------------------------------------

class PhoneNumberChangeView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (WhatsAppThrottle,)

    def post(self, request):
        serializer = PhoneNumberChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_phone = serializer.validated_data['new_phone']
        create_verification_code(
            phone=new_phone,
            purpose=VerificationCode.Purpose.PHONE_CHANGE,
            user=request.user,
            idempotency_key=request.headers.get('Idempotency-Key')
        )
        return Response({'detail': 'Код отправлен на новый номер в WhatsApp.'}, status=status.HTTP_200_OK)


class PhoneChangeConfirmView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (VerifyCodeThrottle,)

    def post(self, request):
        serializer = PhoneChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']

        # Q-2 FIX: `pending` was previously fetched OUTSIDE the transaction,
        # creating a stale-read window. If the VerificationCode row was
        # concurrently invalidated (e.g. user requested a new code which marks
        # old ones is_used=True) between the .first() call and
        # validate_verification_code(), new_phone could come from a different
        # (already-consumed) code than the one the user is confirming.
        #
        # Fix: fetch `pending` inside the atomic block with select_for_update()
        # so the row is locked for the duration of the validation + save.
        with transaction.atomic():
            pending = (
                VerificationCode.objects
                .select_for_update()
                .filter(
                    user=request.user,
                    purpose=VerificationCode.Purpose.PHONE_CHANGE,
                    is_used=False,
                    expires_at__gt=timezone.now(),
                )
                .order_by('-created_at')
                .first()
            )
            if not pending:
                return Response(
                    {'detail': 'Запрос на смену номера не найден или истёк.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_phone = pending.phone

            valid = validate_verification_code(
                phone=new_phone,
                code=code,
                purpose=VerificationCode.Purpose.PHONE_CHANGE,
            )
            if not valid:
                return Response(
                    {'detail': 'Неверный или просроченный код.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # C-4 FIX (CRITICAL — IntegrityError on concurrent phone claim):
            # Two different users can both receive a code for the same new_phone
            # and confirm simultaneously. Each holds a lock on their OWN
            # VerificationCode row (different rows → no mutual exclusion).
            # The first user's save() succeeds; the second hits the UNIQUE
            # constraint on User.phone and raises IntegrityError — which
            # previously propagated as an unhandled 500.
            # Fix: catch IntegrityError and return a 409 with a clear message.
            try:
                request.user.phone = new_phone
                request.user.save(update_fields=['phone'])
            except IntegrityError:
                return Response(
                    {'detail': 'Этот номер телефона уже занят. Укажите другой номер.'},
                    status=status.HTTP_409_CONFLICT,
                )

        blacklist_all_user_tokens(request.user)
        tokens = get_tokens_for_user(request.user)
        return Response(
            {'detail': 'Номер телефона успешно изменён.', **tokens},
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# 2FA via WhatsApp
# ===========================================================================

class TwoFAConfirmView(APIView):
    """POST /accounts/login/2fa/confirm/ — Step 2: подтверждение кода, получение токенов."""
    permission_classes = (AllowAny,)
    throttle_classes = (VerifyCodeThrottle,)

    def post(self, request):
        serializer = TwoFAConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        two_fa_token = serializer.validated_data['two_fa_token']
        code = serializer.validated_data['code']

        session_key = f'{_2FA_CACHE_PREFIX}{two_fa_token}'
        attempts_key = f'{_2FA_ATTEMPTS_PREFIX}{two_fa_token}'

        user_pk = cache.get(session_key)
        if not user_pk:
            return Response(
                {'detail': 'Сессия 2FA истекла или не найдена. Выполните вход заново.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attempts = cache.get(attempts_key, 0)
        if attempts >= _2FA_MAX_ATTEMPTS:
            cache.delete(session_key)
            cache.delete(attempts_key)
            return Response(
                {'detail': 'Превышено количество попыток. Выполните вход заново.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            return Response({'detail': 'Пользователь не найден.'}, status=status.HTTP_404_NOT_FOUND)

        valid = validate_verification_code(
            phone=user.phone,
            code=code,
            purpose=VerificationCode.Purpose.TWO_FA,
        )
        if not valid:
            # C-4 FIX (CRITICAL — Race Condition on brute-force counter):
            # The original code did cache.get() then cache.set(attempts+1) —
            # a non-atomic read-modify-write. 10 concurrent requests all read
            # attempts=0 and all write attempts=1, effectively defeating the
            # 5-attempt brute-force limit (attackers get 5× more tries per wave).
            #
            # Fix: use cache.add() + cache.incr() which map to Redis SETNX +
            # INCR — both are atomic single-command operations.
            #
            #   cache.add()  → Redis SETNX: sets key=0 with TTL only if absent
            #                   (atomic, idempotent — concurrent calls are safe).
            #   cache.incr() → Redis INCR: atomically increments and returns
            #                   the new value regardless of concurrency.
            #
            # The tiny gap between add() and incr() is safe: if two threads
            # race on add(), only one sets the key; both then incr() correctly
            # producing values 1 and 2 (never duplicates of 1).
            cache.add(attempts_key, 0, timeout=_2FA_TTL)
            try:
                new_attempts = cache.incr(attempts_key)
            except ValueError:
                # Fallback for cache backends that don't support incr()
                new_attempts = (cache.get(attempts_key) or 0) + 1
                cache.set(attempts_key, new_attempts, timeout=_2FA_TTL)

            if new_attempts >= _2FA_MAX_ATTEMPTS:
                cache.delete(session_key)
                cache.delete(attempts_key)

            return Response(
                {'detail': 'Неверный или просроченный код.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache.delete(session_key)
        cache.delete(attempts_key)
        user.last_activity = timezone.now()
        user.save(update_fields=['last_activity'])
        tokens = get_tokens_for_user(user)
        return Response(tokens, status=status.HTTP_200_OK)


class TwoFAResendView(APIView):
    """POST /accounts/login/2fa/resend/ — повторная отправка кода без ре-логина."""
    permission_classes = (AllowAny,)
    throttle_classes = (WhatsAppThrottle,)

    def post(self, request):
        two_fa_token = request.data.get('two_fa_token')
        if not two_fa_token:
            return Response(
                {'detail': 'Поле two_fa_token обязательно.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_pk = cache.get(f'{_2FA_CACHE_PREFIX}{two_fa_token}')
        if not user_pk:
            return Response(
                {'detail': 'Сессия 2FA истекла. Выполните вход заново.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            return Response({'detail': 'Пользователь не найден.'}, status=status.HTTP_404_NOT_FOUND)

        create_verification_code(
            phone=user.phone,
            purpose=VerificationCode.Purpose.TWO_FA,
            user=user,
            idempotency_key=request.headers.get('Idempotency-Key')
        )
        cache.set(f'{_2FA_CACHE_PREFIX}{two_fa_token}', user_pk, timeout=_2FA_TTL)
        return Response(
            {'detail': 'Новый код отправлен в WhatsApp.'},
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# 2FA enable / disable
# ===========================================================================

class TwoFAEnableView(APIView):
    """POST /accounts/2fa/enable/"""
    permission_classes = (IsAuthenticated,)
    throttle_classes = (AuthThrottle,)

    def post(self, request):
        if err := _require_password(request):
            return err
        if request.user.is_2fa_enabled:
            return Response({'detail': '2FA уже включена.'}, status=status.HTTP_400_BAD_REQUEST)
        request.user.is_2fa_enabled = True
        request.user.save(update_fields=['is_2fa_enabled'])
        return Response({'detail': '2FA успешно включена.'}, status=status.HTTP_200_OK)


class TwoFADisableView(APIView):
    """POST /accounts/2fa/disable/"""
    permission_classes = (IsAuthenticated,)
    throttle_classes = (AuthThrottle,)

    def post(self, request):
        if err := _require_password(request):
            return err
        if not request.user.is_2fa_enabled:
            return Response({'detail': '2FA уже отключена.'}, status=status.HTTP_400_BAD_REQUEST)
        request.user.is_2fa_enabled = False
        request.user.save(update_fields=['is_2fa_enabled'])
        return Response({'detail': '2FA успешно отключена.'}, status=status.HTTP_200_OK)
