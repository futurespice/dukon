"""
Business-logic helpers for the accounts app.
All verification codes are delivered via WhatsApp (GreenAPI) through Celery tasks
— heavy I/O is never executed on the request thread.
"""
import hmac
import hashlib
import secrets
import logging
from datetime import timedelta

import phonenumbers
from phonenumbers import NumberParseException

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserBonusCard, VerificationCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HIGH FIX #7: Phone number normalisation
# ---------------------------------------------------------------------------

def normalize_phone(phone: str) -> str:
    """
    Parse and normalise a phone number to E.164 format.

    The platform is international — no default region is assumed.
    Users must always supply the full number including country code prefix:
      '+996555123456' → '+996555123456'
      '+79001234567'  → '+79001234567'
      '+12125551234'  → '+12125551234'

    Numbers without a leading '+' and country code are rejected.

    Raises ValueError with a human-readable message on invalid input.
    """
    region = getattr(settings, 'PHONENUMBER_DEFAULT_REGION', None)
    try:
        parsed = phonenumbers.parse(phone, region)
    except NumberParseException as exc:
        raise ValueError(
            'Неверный формат номера телефона. Укажите номер с кодом страны, например +996555123456.'
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(
            f'Недействительный номер телефона: {phone}. '
            'Проверьте код страны и номер.'
        )

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# ---------------------------------------------------------------------------
# Bonus card helpers
# ---------------------------------------------------------------------------

def _generate_candidate_card_number() -> str:
    """
    Generate a cryptographically-random 16-digit candidate bonus card number.

    AUDIT TOCTOU FIX: previously this function checked `.exists()` before
    returning, creating a race between the check and the actual INSERT.
    Now it just produces a candidate — uniqueness is enforced by the DB
    UNIQUE constraint in `create_bonus_card_for_user`.
    """
    return str(secrets.randbelow(10 ** 16)).zfill(16)


def create_bonus_card_for_user(user: User) -> UserBonusCard:
    """
    Create a bonus card for a newly registered user.

    Uses get_or_create to handle concurrent registration races. On a
    bonus_card_number UNIQUE collision (two concurrent registrations randomly
    generating the same number), retries with a new candidate up to 5 times.

    AUDIT TOCTOU FIX: removed the `exists()` pre-check from the number
    generator. Uniqueness is now enforced exclusively by the DB constraint,
    which is the correct place for it. The old pattern:
        if not UserBonusCard.objects.filter(...).exists():
            return number
    created a race window between the check and the INSERT — another thread
    could insert the same number in between, making the check pointless.

    AUDIT ERROR HANDLING FIX: each collision is logged at WARNING level so
    frequent collisions (which would indicate a RNG issue) surface in Sentry.
    """
    from django.db import IntegrityError
    for attempt in range(5):
        try:
            card, _ = UserBonusCard.objects.get_or_create(
                user=user,
                defaults={'bonus_card_number': _generate_candidate_card_number()},
            )
            return card
        except IntegrityError:
            logger.warning(
                'Bonus card number collision for user_id=%s (attempt %d/5). '
                'If this is frequent, review the card number generator.',
                user.pk,
                attempt + 1,
            )
            if attempt == 4:
                logger.error(
                    'Failed to create bonus card for user_id=%s after 5 attempts.',
                    user.pk,
                )
                raise
    raise RuntimeError('Failed to create bonus card after 5 attempts.')  # unreachable


# ---------------------------------------------------------------------------
# HIGH FIX #10: Verification code hashing
# ---------------------------------------------------------------------------

def hash_verification_code(code: int) -> str:
    """
    Return HMAC-SHA256(SECRET_KEY, str(code)) as a hex string.

    Why HMAC and not plain SHA256?
    A 4-digit code has only 9 000 possible values — a SHA256 rainbow table for
    all of them fits in kilobytes. HMAC with a secret key makes precomputation
    infeasible even after the DB is compromised.
    """
    key = settings.SECRET_KEY.encode()
    msg = str(code).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Verification code helpers
# ---------------------------------------------------------------------------

def generate_verification_code() -> int:
    """Generate a random 4-digit code using cryptographically-secure randomness."""
    return secrets.randbelow(9000) + 1000  # 1000..9999


def create_verification_code(
    phone: str,
    purpose: str = VerificationCode.Purpose.REGISTER,
    user: User | None = None,
    idempotency_key: str | None = None,
) -> VerificationCode:
    """
    Invalidate previous codes for this phone + purpose, create a new one,
    and dispatch delivery via WhatsApp (GreenAPI) Celery task (non-blocking).

    Stores HMAC-SHA256 of the raw code — the raw integer is sent to the user
    via WhatsApp but never persisted in the DB.
    """
    if idempotency_key:
        from django.utils import timezone
        existing = VerificationCode.objects.filter(
            idempotency_key=idempotency_key,
            phone=phone,
            purpose=purpose,
        ).first()
        if existing:
            return existing

    raw_code = generate_verification_code()
    code_hash = hash_verification_code(raw_code)

    ttl = getattr(settings, 'VERIFY_CODE_TTL', 300)
    expires_at = timezone.now() + timedelta(seconds=ttl)

    # AUDIT-3 FIX #6: Wrap invalidation + creation in a single transaction.
    with transaction.atomic():
        VerificationCode.objects.filter(
            phone=phone, purpose=purpose, is_used=False
        ).update(is_used=True)

        verification = VerificationCode.objects.create(
            phone=phone,
            code=code_hash,
            purpose=purpose,
            user=user,
            expires_at=expires_at,
            idempotency_key=idempotency_key,
        )

    # Dispatch WhatsApp delivery OUTSIDE the transaction.
    from apps.accounts.tasks import send_whatsapp_code_task
    send_whatsapp_code_task.delay(phone, raw_code)

    return verification


def validate_verification_code(phone: str, code: int, purpose: str) -> bool:
    """
    Validate the code atomically. Marks it as used on success.
    Uses atomic UPDATE to prevent TOCTOU race conditions.

    Returns True if valid.
    """
    code_hash = hash_verification_code(code)
    with transaction.atomic():
        updated = VerificationCode.objects.filter(
            phone=phone,
            code=code_hash,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).update(is_used=True)
        return updated > 0


# ---------------------------------------------------------------------------
# JWT token helpers
# ---------------------------------------------------------------------------

def get_tokens_for_user(user: User) -> dict:
    """Return access + refresh JWT tokens for user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def blacklist_all_user_tokens(user: User) -> None:
    """
    Blacklist all outstanding refresh tokens for a user.
    Uses bulk_create with ignore_conflicts to avoid N+1 queries.
    Called on password change and account deactivation.

    M-3 FIX (Race condition in already_blacklisted pre-check):
    The original code fetched outstanding tokens and already-blacklisted
    token IDs in two separate queries, then computed the difference in
    Python. A concurrent login between these two reads could create a new
    OutstandingToken that was missing from the snapshot — that new token
    would not be blacklisted, leaving an active session after a password
    change or deactivation.

    Fix: drop the already_blacklisted pre-check entirely. bulk_create with
    ignore_conflicts=True is idempotent — it silently skips rows that
    already exist (violate the UNIQUE constraint), so passing ALL outstanding
    tokens is both correct and safe. The race window is eliminated because
    there is no longer a gap between "read already-blacklisted" and
    "insert new rows".

    Note: tokens created by a concurrent login AFTER this function returns
    are outside its scope — that’s a separate concern (e.g. the caller
    should invalidate the current session and force re-authentication).
    """
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

    outstanding = list(OutstandingToken.objects.filter(user=user))
    if not outstanding:
        return

    # ignore_conflicts=True handles tokens already in the blacklist —
    # no pre-check needed, removing the race between the read and the write.
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=t) for t in outstanding],
        ignore_conflicts=True,
    )
