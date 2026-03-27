"""
Critical tests for products app — covers AUDIT-3 cross-store validation fixes.

Tests verify:
- CategorySerializer.validate() cross-store parent on PATCH (AUDIT-3 #5)
- ProductSerializer cross-store category on PATCH (AUDIT-3 #11)
- ids type validation in bulk endpoints (AUDIT-3 #15)
"""
import pytest
from decimal import Decimal

from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.services import create_bonus_card_for_user
from apps.stores.models import Store
from apps.products.models import Category, Product, ProductModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner_a(db):
    user = User.objects.create_user(
        phone='+996700300001',
        password='ownerA123',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def owner_b(db):
    user = User.objects.create_user(
        phone='+996700300002',
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


@pytest.fixture
def cat_a(db, store_a):
    return Category.objects.create(name='Cat A', store=store_a)


@pytest.fixture
def cat_b(db, store_b):
    return Category.objects.create(name='Cat B', store=store_b)


@pytest.fixture
def product_a(db, store_a, cat_a):
    return Product.objects.create(
        name='Product A',
        short_description='Test',
        store=store_a,
        category=cat_a,
    )


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #5: Cross-store parent category on PATCH
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_category_patch_cross_store_parent_rejected(api_client, owner_a, cat_a, cat_b):
    """PATCH category with parent from another store must fail."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.patch(
        f'/api/v1/products/categories/{cat_a.pk}/',
        {'parent': cat_b.pk},
        format='json',
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_category_patch_same_store_parent_allowed(api_client, owner_a, store_a, cat_a):
    """PATCH category with parent from the same store should work."""
    parent = Category.objects.create(name='Parent', store=store_a)
    api_client.force_authenticate(user=owner_a)
    resp = api_client.patch(
        f'/api/v1/products/categories/{cat_a.pk}/',
        {'parent': parent.pk},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK
    cat_a.refresh_from_db()
    assert cat_a.parent_id == parent.pk


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #11: Cross-store category on product PATCH
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_product_patch_cross_store_category_rejected(api_client, owner_a, product_a, cat_b):
    """PATCH product with category from another store must fail."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.patch(
        f'/api/v1/products/{product_a.pk}/',
        {'category': cat_b.pk},
        format='json',
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_product_patch_same_store_category_allowed(api_client, owner_a, product_a, store_a):
    """PATCH product with category from the same store should work."""
    new_cat = Category.objects.create(name='New Cat', store=store_a)
    api_client.force_authenticate(user=owner_a)
    resp = api_client.patch(
        f'/api/v1/products/{product_a.pk}/',
        {'category': new_cat.pk},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK
    product_a.refresh_from_db()
    assert product_a.category_id == new_cat.pk


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #15: ids type validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_category_bulk_delete_rejects_non_list_ids(api_client, owner_a):
    """ids must be a list."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.post(
        '/api/v1/products/categories/multiple-delete/',
        {'ids': 'not-a-list'},
        format='json',
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_product_bulk_delete_rejects_dict_ids(api_client, owner_a):
    """ids as dict must be rejected."""
    api_client.force_authenticate(user=owner_a)
    resp = api_client.post(
        '/api/v1/products/multiple-delete/',
        {'ids': {'key': 'val'}},
        format='json',
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
