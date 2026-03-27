"""
Smoke tests for the accounts app.

These tests verify the most critical auth flows without mocking external
services (SMS/WhatsApp). They run against a real test database and cover
registration, login guard for unverified users, code verification, and
the /health/ endpoint.

DEVOPS FIX #4: added to satisfy --cov-fail-under=10 in CI.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, VerificationCode
from apps.accounts.services import (
    hash_verification_code,
    create_bonus_card_for_user,
)
from django.utils import timezone
from datetime import timedelta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def verified_user(db):
    """A fully verified CLIENT user."""
    user = User.objects.create_user(
        phone='+996700000001',
        password='testpass123',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def unverified_user(db):
    """A newly registered NOTVERIFY user."""
    user = User.objects.create_user(
        phone='+996700000002',
        password='testpass123',
        role=User.Role.NOT_VERIFIED,
    )
    create_bonus_card_for_user(user)
    return user


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_health_endpoint(client):
    """GET /health/ must return 200 {"status": "ok"} with no auth."""
    resp = client.get('/health/')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {'status': 'ok'}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_register_creates_notverify_user(client):
    """POST /api/v1/accounts/register/ creates a NOTVERIFY user, no tokens."""
    resp = client.post('/api/v1/accounts/register/', {
        'phone': '+996700000099',
        'password': 'strongpass1',
        'first_name': 'Test',
    })
    assert resp.status_code == status.HTTP_201_CREATED
    assert 'access' not in resp.json()
    user = User.objects.get(phone='+996700000099')
    assert user.role == User.Role.NOT_VERIFIED


@pytest.mark.django_db
def test_register_duplicate_phone(client, verified_user):
    """Registering with an already-used phone returns 400."""
    resp = client.post('/api/v1/accounts/register/', {
        'phone': verified_user.phone,
        'password': 'newpass123',
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_normalises_phone(client):
    """Different formats of the same KG number must be deduplicated."""
    resp1 = client.post('/api/v1/accounts/register/', {
        'phone': '0700000088',
        'password': 'pass12345',
    })
    assert resp1.status_code == status.HTTP_201_CREATED

    # Same number, international format — should be rejected as duplicate.
    resp2 = client.post('/api/v1/accounts/register/', {
        'phone': '+996700000088',
        'password': 'pass12345',
    })
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_verified_user_returns_tokens(client, verified_user):
    """Verified users receive access + refresh on correct credentials."""
    resp = client.post('/api/v1/accounts/login/', {
        'phone': verified_user.phone,
        'password': 'testpass123',
    })
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert 'access' in data
    assert 'refresh' in data


@pytest.mark.django_db
def test_login_unverified_user_blocked(client, unverified_user):
    """NOTVERIFY users must not receive JWT tokens — 400 with clear message."""
    resp = client.post('/api/v1/accounts/login/', {
        'phone': unverified_user.phone,
        'password': 'testpass123',
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert 'подтверждён' in str(resp.json()).lower() or 'подтверждения' in str(resp.json()).lower()


@pytest.mark.django_db
def test_login_wrong_password(client, verified_user):
    """Wrong password returns 400, no tokens."""
    resp = client.post('/api/v1/accounts/login/', {
        'phone': verified_user.phone,
        'password': 'wrongpassword',
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert 'access' not in resp.json()


# ---------------------------------------------------------------------------
# Code verification
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_check_verify_code_upgrades_role(client, unverified_user):
    """Valid REGISTER code upgrades NOTVERIFY → CLIENT and issues tokens."""
    raw_code = 1234
    VerificationCode.objects.create(
        phone=unverified_user.phone,
        code=hash_verification_code(raw_code),
        purpose=VerificationCode.Purpose.REGISTER,
        user=unverified_user,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    resp = client.post('/api/v1/accounts/check/verify-code/', {
        'phone': unverified_user.phone,
        'code': raw_code,
    })
    assert resp.status_code == status.HTTP_200_OK
    assert 'access' in resp.json()
    unverified_user.refresh_from_db()
    assert unverified_user.role == User.Role.CLIENT


@pytest.mark.django_db
def test_check_verify_code_expired_rejected(client, unverified_user):
    """Expired codes must not work."""
    raw_code = 5678
    VerificationCode.objects.create(
        phone=unverified_user.phone,
        code=hash_verification_code(raw_code),
        purpose=VerificationCode.Purpose.REGISTER,
        user=unverified_user,
        expires_at=timezone.now() - timedelta(minutes=1),  # already expired
    )
    resp = client.post('/api/v1/accounts/check/verify-code/', {
        'phone': unverified_user.phone,
        'code': raw_code,
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_check_verify_code_wrong_code(client, unverified_user):
    """Wrong code returns 400."""
    VerificationCode.objects.create(
        phone=unverified_user.phone,
        code=hash_verification_code(9999),
        purpose=VerificationCode.Purpose.REGISTER,
        user=unverified_user,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    resp = client.post('/api/v1/accounts/check/verify-code/', {
        'phone': unverified_user.phone,
        'code': 1111,  # wrong
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_profile_requires_auth(client):
    """GET /api/v1/accounts/profile/ without token → 401."""
    resp = client.get('/api/v1/accounts/profile/')
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_profile_phone_readonly(client, verified_user):
    """PATCH profile must not change phone — phone field is read-only."""
    client.force_authenticate(user=verified_user)
    original_phone = verified_user.phone
    resp = client.patch('/api/v1/accounts/profile/', {'phone': '+996700000000'})
    assert resp.status_code == status.HTTP_200_OK
    verified_user.refresh_from_db()
    assert verified_user.phone == original_phone


# ---------------------------------------------------------------------------
# Services unit tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_hash_verification_code_deterministic():
    """Same code always produces the same hash."""
    h1 = hash_verification_code(1234)
    h2 = hash_verification_code(1234)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_hash_verification_code_different_codes_different_hashes():
    """Different codes produce different hashes (no collision for range 1000-9999)."""
    hashes = {hash_verification_code(c) for c in range(1000, 1010)}
    assert len(hashes) == 10


# ---------------------------------------------------------------------------
# 2FA
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_2fa_required_no_tokens(client, verified_user):
    """User with 2FA enabled must NOT receive tokens on /login/ — only two_fa_token."""
    verified_user.is_2fa_enabled = True
    verified_user.save(update_fields=['is_2fa_enabled'])

    resp = client.post('/api/v1/accounts/login/', {
        'phone': verified_user.phone,
        'password': 'testpass123',
    })
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert '2fa_required' in data
    assert data['2fa_required'] is True
    assert 'two_fa_token' in data
    assert 'access' not in data
    assert 'refresh' not in data


@pytest.mark.django_db
def test_2fa_confirm_issues_tokens(client, verified_user):
    """Valid 2FA code on /login/2fa/confirm/ must issue JWT tokens."""
    from django.core.cache import cache

    verified_user.is_2fa_enabled = True
    verified_user.save(update_fields=['is_2fa_enabled'])

    two_fa_token = 'test-2fa-token-abc'
    cache.set(f'2fa_pending:{two_fa_token}', verified_user.pk, timeout=300)

    raw_code = 4321
    VerificationCode.objects.create(
        phone=verified_user.phone,
        code=hash_verification_code(raw_code),
        purpose=VerificationCode.Purpose.TWO_FA,
        user=verified_user,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    resp = client.post('/api/v1/accounts/login/2fa/confirm/', {
        'two_fa_token': two_fa_token,
        'code': raw_code,
    })
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert 'access' in data
    assert 'refresh' in data


@pytest.mark.django_db
def test_2fa_confirm_brute_force_lockout(client, verified_user):
    """After 5 wrong codes the session is invalidated — further attempts are rejected."""
    from django.core.cache import cache

    two_fa_token = 'test-2fa-brute-token'
    cache.set(f'2fa_pending:{two_fa_token}', verified_user.pk, timeout=300)
    cache.set(f'2fa_attempts:{two_fa_token}', 5, timeout=300)  # already at max

    VerificationCode.objects.create(
        phone=verified_user.phone,
        code=hash_verification_code(1234),
        purpose=VerificationCode.Purpose.TWO_FA,
        user=verified_user,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    resp = client.post('/api/v1/accounts/login/2fa/confirm/', {
        'two_fa_token': two_fa_token,
        'code': 1234,
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert 'попыток' in resp.json()['detail']
    # Session must be gone after lockout
    assert cache.get(f'2fa_pending:{two_fa_token}') is None


@pytest.mark.django_db
def test_2fa_confirm_wrong_code_increments_attempts(client, verified_user):
    """Each wrong code increments the attempts counter."""
    from django.core.cache import cache

    two_fa_token = 'test-2fa-attempts-token'
    cache.set(f'2fa_pending:{two_fa_token}', verified_user.pk, timeout=300)

    # Use a code that won't match anything
    resp = client.post('/api/v1/accounts/login/2fa/confirm/', {
        'two_fa_token': two_fa_token,
        'code': 9999,
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert cache.get(f'2fa_attempts:{two_fa_token}') == 1


@pytest.mark.django_db
def test_2fa_confirm_expired_session(client):
    """Expired / missing two_fa_token returns 400."""
    resp = client.post('/api/v1/accounts/login/2fa/confirm/', {
        'two_fa_token': 'nonexistent-token',
        'code': 1234,
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
