"""
Smoke tests for the stores app.
"""
import pytest
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.services import create_bonus_card_for_user
from apps.stores.models import Store


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def owner(db):
    user = User.objects.create_user(
        phone='+996722000001',
        password='pass12345',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def other_user(db):
    user = User.objects.create_user(
        phone='+996722000002',
        password='pass12345',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def store(db, owner):
    return Store.objects.create(
        name='My Store',
        address='Bishkek',
        admin_user=owner,
    )


# ---------------------------------------------------------------------------
# Public listing — balance must not be visible
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_store_list_public(client, store):
    """GET /api/v1/stores/ is public and does not expose balance."""
    resp = client.get('/api/v1/stores/')
    assert resp.status_code == status.HTTP_200_OK
    results = resp.json()['results']
    assert len(results) >= 1
    # balance must NOT appear in the public serializer
    assert 'balance' not in results[0]


@pytest.mark.django_db
def test_store_detail_public_no_balance(client, store):
    """GET /api/v1/stores/{uuid}/ is public and does not expose balance."""
    resp = client.get(f'/api/v1/stores/{store.uuid}/')
    assert resp.status_code == status.HTTP_200_OK
    assert 'balance' not in resp.json()


# ---------------------------------------------------------------------------
# Create store
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_store_sets_admin_user(client, owner):
    """POST /api/v1/stores/ always sets admin_user to the requesting user."""
    client.force_authenticate(user=owner)
    resp = client.post('/api/v1/stores/', {
        'name': 'New Store',
        'address': 'Test St 1',
        'admin_user': 99999,  # attempt to hijack — must be ignored
    }, format='json')
    assert resp.status_code == status.HTTP_201_CREATED
    # admin_user in the response must be the authenticated user, not 99999
    assert resp.json()['admin_user'] == owner.pk


@pytest.mark.django_db
def test_create_store_notverify_blocked(client, db):
    """NOTVERIFY users cannot create stores."""
    unverified = User.objects.create_user(
        phone='+996722000099',
        password='pass12345',
        role=User.Role.NOT_VERIFIED,
    )
    client.force_authenticate(user=unverified)
    resp = client.post('/api/v1/stores/', {
        'name': 'Sneaky Store',
        'address': 'Bishkek',
    }, format='json')
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_update_store_owner_allowed(client, owner, store):
    """Owner can update their own store."""
    client.force_authenticate(user=owner)
    resp = client.patch(f'/api/v1/stores/{store.uuid}/', {'name': 'Renamed'}, format='json')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['name'] == 'Renamed'


@pytest.mark.django_db
def test_update_store_non_owner_forbidden(client, other_user, store):
    """Non-owner cannot update another user's store."""
    client.force_authenticate(user=other_user)
    resp = client.patch(f'/api/v1/stores/{store.uuid}/', {'name': 'Hacked'}, format='json')
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_multiple_delete_returns_count(client, owner, store):
    """POST /api/v1/stores/multiple-delete/ returns {"deleted": N}."""
    client.force_authenticate(user=owner)
    resp = client.post('/api/v1/stores/multiple-delete/', {'ids': [str(store.uuid)]}, format='json')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['deleted'] == 1


@pytest.mark.django_db
def test_multiple_delete_wrong_owner_returns_zero(client, other_user, store):
    """Deleting a store you don't own returns {"deleted": 0}, not an error."""
    client.force_authenticate(user=other_user)
    resp = client.post('/api/v1/stores/multiple-delete/', {'ids': [str(store.uuid)]}, format='json')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['deleted'] == 0


# ---------------------------------------------------------------------------
# Bank details — must be private
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bank_details_require_auth(client):
    """GET /api/v1/stores/bank-details/ requires authentication."""
    resp = client.get('/api/v1/stores/bank-details/')
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
