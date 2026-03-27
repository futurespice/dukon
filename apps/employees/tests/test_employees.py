"""
Critical tests for employees app — covers AUDIT-3 security fixes.

Tests verify:
- IDOR: cannot create employee in another user's store (AUDIT-3 #2)
- Token TTL enforcement (AUDIT-3 #7)
- ids type validation in bulk delete (AUDIT-3 #15)
"""
import pytest
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.services import create_bonus_card_for_user
from apps.stores.models import Store
from apps.employees.models import Employee


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner_a(db):
    user = User.objects.create_user(
        phone='+996700200001',
        password='ownerA123',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def owner_b(db):
    user = User.objects.create_user(
        phone='+996700200002',
        password='ownerB123',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def store_a(db, owner_a):
    return Store.objects.create(name='Store A', address='Addr A', admin_user=owner_a)


@pytest.fixture
def store_b(db, owner_b):
    return Store.objects.create(name='Store B', address='Addr B', admin_user=owner_b)


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #2: IDOR — cannot create employee in other's store
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_employee_in_own_store(api_client, owner_a, store_a):
    """Owner A can create an employee in Store A."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.post('/api/v1/employees/', {
        'store': store_a.uuid,
        'username': 'emp_in_a',
        'password': 'emp12345',
        'first_name': 'Test',
        'position': 'CASHIER',
    }, format='json')
    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_idor_create_employee_in_others_store(api_client, owner_a, store_b):
    """Owner A must NOT be able to create an employee in Store B."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.post('/api/v1/employees/', {
        'store': store_b.uuid,
        'username': 'spy_account',
        'password': 'spy12345',
        'first_name': 'Spy',
        'position': 'CASHIER',
    }, format='json')
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert Employee.objects.filter(username='spy_account').count() == 0


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #7: Token TTL
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_employee_token_valid_within_ttl(db, store_a):
    """Fresh token should be valid."""
    emp = Employee.objects.create(
        store=store_a,
        username='ttl_test',
        first_name='TTL',
        position='WAITER',
    )
    assert emp.is_token_valid(max_age_hours=24) is True


@pytest.mark.django_db
def test_employee_token_expired(db, store_a):
    """Token older than TTL should be invalid."""
    emp = Employee.objects.create(
        store=store_a,
        username='expired_test',
        first_name='Expired',
        position='WAITER',
    )
    # Manually backdate the token creation
    Employee.objects.filter(pk=emp.pk).update(
        token_created_at=timezone.now() - timedelta(hours=25)
    )
    emp.refresh_from_db()
    assert emp.is_token_valid(max_age_hours=24) is False


@pytest.mark.django_db
def test_refresh_token_updates_created_at(db, store_a):
    """refresh_token() must reset token_created_at."""
    emp = Employee.objects.create(
        store=store_a,
        username='refresh_test',
        first_name='Refresh',
        position='WAITER',
    )
    old_token = emp.token
    old_created = emp.token_created_at

    emp.refresh_token()
    assert emp.token != old_token
    assert emp.token_created_at >= old_created


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #15: ids type validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bulk_delete_rejects_non_list_ids(api_client, owner_a):
    """ids must be a list."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.post('/api/v1/employees/multiple-delete/', {
        'ids': 'abc',
    }, format='json')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Employee login / logout
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_employee_login_returns_token(api_client, store_a):
    """Valid credentials return the session token."""
    from django.contrib.auth.hashers import make_password
    emp = Employee.objects.create(
        store=store_a,
        username='login_test',
        password=make_password('pass12345'),
        first_name='Login',
        position='CASHIER',
    )
    resp = api_client.post('/api/v1/employees/auth/login/', {
        'username': 'login_test',
        'password': 'pass12345',
    })
    assert resp.status_code == status.HTTP_200_OK
    assert 'token' in resp.json()


@pytest.mark.django_db
def test_employee_login_wrong_password(api_client, store_a):
    """Wrong password returns 400."""
    from django.contrib.auth.hashers import make_password
    Employee.objects.create(
        store=store_a,
        username='login_fail',
        password=make_password('correct'),
        first_name='Fail',
        position='CASHIER',
    )
    resp = api_client.post('/api/v1/employees/auth/login/', {
        'username': 'login_fail',
        'password': 'wrong',
    })
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
