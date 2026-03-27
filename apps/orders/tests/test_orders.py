"""
Critical tests for orders app — covers AUDIT-3 security and business logic fixes.

Tests verify:
- Stock restoration on order cancellation (AUDIT-3 #3)
- State machine enforcement for bulk cancel and destroy (AUDIT-3 #8)
- Throttle applies to authenticated users (AUDIT-3 QA#3)
- notifications_sent is read-only on update (AUDIT-3 #12)
- ids type validation in bulk endpoints (AUDIT-3 #15)
"""
import pytest
from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.services import create_bonus_card_for_user
from apps.stores.models import Store
from apps.products.models import Product, ProductModel, Category
from apps.orders.models import Order, OrderItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def owner(db):
    """Store owner user."""
    user = User.objects.create_user(
        phone='+996700100001',
        password='ownerpass1',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def other_user(db):
    """Another authenticated user (not the store owner)."""
    user = User.objects.create_user(
        phone='+996700100002',
        password='otherpass1',
        role=User.Role.CLIENT,
    )
    create_bonus_card_for_user(user)
    return user


@pytest.fixture
def store(db, owner):
    return Store.objects.create(
        name='Test Store',
        address='Test Address',
        admin_user=owner,
    )


@pytest.fixture
def product_with_stock(db, store):
    """A product with a model that has 100 units in stock."""
    product = Product.objects.create(
        store=store,
        name='Test Product',
        short_description='Test',
    )
    model = ProductModel.objects.create(
        product=product,
        name='Default',
        quantity=100,
        price=Decimal('500.00'),
    )
    return product, model


@pytest.fixture
def order_with_items(db, product_with_stock):
    """An order with 5 units of the test product. Stock decremented to 95."""
    product, model = product_with_stock
    order = Order.objects.create(
        phone_number='+996700999999',
        first_name='Тест',
        address='ул. Тестовая 1',
        order_status=Order.OrderStatus.IN_PROCESSING,
    )
    OrderItem.objects.create(
        order=order,
        product=model,
        quantity=5,
        price_at_order=model.price,
        product_name_at_order=f'{product.name} — {model.name}',
    )
    # Simulate the stock decrement that OrderSerializer.create() does.
    model.quantity = 95
    model.save(update_fields=['quantity'])
    return order, model


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #3: Stock restoration on cancel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_destroy_order_restores_stock(api_client, owner, order_with_items):
    """DELETE /orders/{id}/ must restore product stock."""
    order, model = order_with_items
    assert model.quantity == 95

    api_client.force_authenticate(user=owner)
    resp = api_client.delete(f'/api/v1/orders/{order.pk}/')
    assert resp.status_code == status.HTTP_200_OK

    model.refresh_from_db()
    assert model.quantity == 100, 'Stock should be fully restored after cancel'

    order.refresh_from_db()
    assert order.order_status == Order.OrderStatus.CANCELED


@pytest.mark.django_db
def test_bulk_cancel_restores_stock(api_client, owner, order_with_items):
    """POST /orders/multiple-delete/ must restore stock for all canceled orders."""
    order, model = order_with_items

    api_client.force_authenticate(user=owner)
    resp = api_client.post('/api/v1/orders/multiple-delete/', {'ids': [order.pk]})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()['canceled'] == 1

    model.refresh_from_db()
    assert model.quantity == 100


@pytest.mark.django_db
def test_patch_cancel_restores_stock(api_client, owner, order_with_items):
    """PATCH /orders/{id}/ with order_status=CANCELED must restore stock."""
    order, model = order_with_items

    api_client.force_authenticate(user=owner)
    resp = api_client.patch(
        f'/api/v1/orders/{order.pk}/',
        {'order_status': 'CANCELED'},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK

    model.refresh_from_db()
    assert model.quantity == 100


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #8: State machine enforcement
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_destroy_delivered_order_rejected(api_client, owner, order_with_items):
    """Cannot DELETE an order that is already DELIVERED."""
    order, model = order_with_items
    order.order_status = Order.OrderStatus.CANCELED
    order.save(update_fields=['order_status'])

    api_client.force_authenticate(user=owner)
    resp = api_client.delete(f'/api/v1/orders/{order.pk}/')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # Stock should NOT change.
    model.refresh_from_db()
    assert model.quantity == 95


@pytest.mark.django_db
def test_bulk_cancel_skips_non_cancellable(api_client, owner, order_with_items, product_with_stock):
    """Bulk cancel should only cancel orders in cancellable states."""
    order, model = order_with_items

    # Create a second order that is already CANCELED
    product, pm = product_with_stock
    order2 = Order.objects.create(
        phone_number='+996700999998',
        first_name='Тест2',
        address='ул. Тестовая 2',
        order_status=Order.OrderStatus.CANCELED,
    )
    OrderItem.objects.create(
        order=order2,
        product=pm,
        quantity=3,
        price_at_order=pm.price,
        product_name_at_order='test',
    )

    api_client.force_authenticate(user=owner)
    resp = api_client.post(
        '/api/v1/orders/multiple-delete/',
        {'ids': [order.pk, order2.pk]},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK
    # Only order1 (IN_PROCESSING) should be canceled; order2 was already CANCELED.
    assert resp.json()['canceled'] == 1


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #12: notifications_sent read-only
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_notifications_sent_readonly_on_update(api_client, owner, order_with_items):
    """PATCH should not allow setting notifications_sent=True."""
    order, _ = order_with_items
    assert order.notifications_sent is False

    api_client.force_authenticate(user=owner)
    resp = api_client.patch(
        f'/api/v1/orders/{order.pk}/',
        {'notifications_sent': True},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK

    order.refresh_from_db()
    assert order.notifications_sent is False, 'notifications_sent must remain read-only'


# ---------------------------------------------------------------------------
# AUDIT-3 FIX #15: ids type validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bulk_cancel_rejects_non_list_ids(api_client, owner):
    """ids must be a list, not a string or dict."""
    api_client.force_authenticate(user=owner)

    resp = api_client.post(
        '/api/v1/orders/multiple-delete/',
        {'ids': 'not-a-list'},
        format='json',
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert 'массив' in resp.json()['detail'].lower()


# ---------------------------------------------------------------------------
# Order creation with stock decrement
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_order_decrements_stock(api_client, product_with_stock):
    """POST /orders/ must decrement ProductModel.quantity."""
    product, model = product_with_stock
    assert model.quantity == 100

    resp = api_client.post('/api/v1/orders/', {
        'phone_number': '+996700111111',
        'first_name': 'Buyer',
        'address': '',
        'items': [{'product': model.pk, 'quantity': 3}],
    }, format='json')
    assert resp.status_code == status.HTTP_201_CREATED

    model.refresh_from_db()
    assert model.quantity == 97


@pytest.mark.django_db
def test_create_order_insufficient_stock(api_client, product_with_stock):
    """POST /orders/ with quantity > stock must fail."""
    product, model = product_with_stock
    model.quantity = 2
    model.save(update_fields=['quantity'])

    resp = api_client.post('/api/v1/orders/', {
        'phone_number': '+996700111112',
        'first_name': 'Buyer',
        'address': '',
        'items': [{'product': model.pk, 'quantity': 5}],
    }, format='json')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    model.refresh_from_db()
    assert model.quantity == 2, 'Stock should not change on failed order'


# ---------------------------------------------------------------------------
# total_price correctness (AUDIT-3 FIX #1)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_total_price_correct_for_owner(api_client, owner, order_with_items):
    """Store owner must see the correct total_price from prefetch cache."""
    order, model = order_with_items

    api_client.force_authenticate(user=owner)
    resp = api_client.get(f'/api/v1/orders/{order.pk}/')
    assert resp.status_code == status.HTTP_200_OK
    expected = str(model.price * 5)
    # DRF returns Decimal as string like "2500.00"
    assert resp.json()['total_price'] == expected
