"""
Business-logic services for the orders app.

Extracted from views.py and serializers.py where cancel+restore-stock logic
was duplicated in three places:
  1. OrderDetailView.destroy()
  2. OrderMultipleDeleteView.post()
  3. OrderUpdateSerializer.update()  (was_canceled branch)

All three now call cancel_order() / restore_stock_for_order_items() from here.
"""
import logging
from collections import defaultdict

from django.db import transaction
from django.db.models import F, Case, When, IntegerField

logger = logging.getLogger(__name__)


def restore_stock_for_order_items(items) -> None:
    """
    Restore product stock for an iterable of OrderItem instances.

    Uses F() expressions to avoid read-modify-write races.
    Caller is responsible for wrapping this in transaction.atomic().

    Args:
        items: Iterable of OrderItem instances (may come from prefetch cache).
    """
    from apps.products.models import ProductModel

    for item in items:
        if item.product_id:
            ProductModel.objects.filter(pk=item.product_id).update(
                quantity=F('quantity') + item.quantity
            )


@transaction.atomic
def cancel_order(order) -> None:
    """
    Cancel a single order and restore stock for all its items atomically.

    C-1 FIX (CRITICAL — Double Stock Restoration):
    Previously this function received `order` without a row-level lock.
    Two concurrent DELETE requests could both read status=IN_PROCESSING,
    both call restore_stock_for_order_items(), and both mark CANCELED.
    Result: inventory inflated by 2× the restored quantities.

    Fix: re-fetch the order with select_for_update() inside the transaction
    to acquire a row-level lock BEFORE reading its status. The idempotency
    guard ("already CANCELED → return") ensures whichever request wins the
    lock will restore stock; the loser silently exits.

    Args:
        order: Order instance — used only to obtain the PK.
               The locked row is always fetched fresh from DB here.

    Side effects:
        - Sets order.order_status = CANCELED and saves update_fields.
        - Increments ProductModel.quantity for each OrderItem.
    """
    from apps.orders.models import Order

    # C-1 FIX: acquire a row-level lock so only ONE concurrent request
    # can proceed past this point for a given order pk.
    locked_order = Order.objects.select_for_update().get(pk=order.pk)

    # C-1 FIX (CRITICAL — Terminal-State Guard extended to REJECTED):
    # The original guard only checked CANCELED. A concurrent PATCH could move
    # the order to REJECTED (stock NOT restored by that path), and then a
    # concurrent DELETE read the stale ACCEPTED status, passed the pre-check,
    # and called cancel_order() which saw REJECTED != CANCELED → proceeded to
    # restore stock → stock inflated.
    #
    # TERMINAL_STATUSES contains every state from which stock must NOT be
    # restored a second time:
    #   - CANCELED: stock already restored by whoever set this status.
    #   - REJECTED: stock was never deducted after rejection (the order never
    #     moved product out of the warehouse on its own), so restoring here
    #     would inflate inventory.
    _TERMINAL_STATUSES = {Order.OrderStatus.CANCELED, Order.OrderStatus.REJECTED}
    if locked_order.order_status in _TERMINAL_STATUSES:
        logger.info(
            'cancel_order: order id=%s already in terminal state %r — '
            'skipping to prevent double stock restoration.',
            order.pk,
            locked_order.order_status,
        )
        return

    restore_stock_for_order_items(locked_order.items.all())

    locked_order.order_status = Order.OrderStatus.CANCELED
    locked_order.save(update_fields=['order_status', 'updated_at'])

    logger.info('order_canceled id=%s via cancel_order()', order.pk)


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------

@transaction.atomic
def create_order(validated_data: dict) -> 'Order':
    """
    A-3 REFACTOR: extracted from OrderSerializer.create().

    Creates an Order with its OrderItems and atomically decrements
    product stock. All stock checks are performed under row-level locks
    to prevent race conditions and negative inventory.

    Args:
        validated_data: deserialized and validated data dict from
                        OrderSerializer. Must include 'items' key with a
                        list of dicts each containing 'product' and 'quantity'.

    Returns:
        The newly created Order instance.

    Raises:
        rest_framework.serializers.ValidationError: on stock errors or
        missing products (propagated directly to the serializer layer).
    """
    from rest_framework import serializers as drf_serializers
    from apps.orders.models import Order, OrderItem
    from apps.products.models import ProductModel

    items_data = validated_data.pop('items')

    # Lock all referenced product rows in deterministic order to prevent
    # deadlocks with concurrent order creation.
    product_ids = [item['product'].pk for item in items_data]
    locked_products = {
        p.pk: p
        for p in ProductModel.objects.select_for_update().filter(
            pk__in=sorted(set(product_ids))
        )
    }

    missing = [
        item['product'].pk for item in items_data
        if item['product'].pk not in locked_products
    ]
    if missing:
        raise drf_serializers.ValidationError(
            {'items': [f'Товар с id={pk} не найден или был удалён.' for pk in missing]}
        )

    # C-NEW-2 FIX (CRITICAL — Negative Stock on duplicate product_ids):
    # The stock check MUST use the same aggregated totals as the inventory
    # UPDATE that follows. Checking each item individually allows this case:
    #
    #   product_id=5, stock=4, items=[{qty:3}, {qty:2}]
    #   Per-item check:  4 < 3? No.  4 < 2? No.  → no error
    #   Aggregated debit: 3 + 2 = 5  →  UPDATE quantity = 4 - 5 = -1  ← MINUS!
    #
    # Fix: aggregate total demanded quantity per product_id FIRST, then
    # compare the SUM against the locked stock value. This is the same dict
    # used in the UPDATE, so check and debit are always consistent.
    qty_by_product_id: dict[int, int] = defaultdict(int)
    for item in items_data:
        qty_by_product_id[item['product'].pk] += item['quantity']

    stock_errors = []
    for product_pk, total_qty in qty_by_product_id.items():
        product = locked_products[product_pk]
        if product.quantity < total_qty:
            stock_errors.append(
                f'Товар «{product.product.name} — {product.name}»: '
                f'запрошено {total_qty}, доступно {product.quantity}.'
            )
    if stock_errors:
        raise drf_serializers.ValidationError({'items': stock_errors})

    order = Order.objects.create(**validated_data)

    to_create = []
    for item in items_data:
        product = locked_products[item['product'].pk]
        to_create.append(OrderItem(
            order=order,
            product=product,
            quantity=item['quantity'],
            price_at_order=product.price,
            product_name_at_order=f'{product.product.name} — {product.name}',
        ))
    OrderItem.objects.bulk_create(to_create)

    # Decrement inventory atomically via Case/When in a single UPDATE.
    # qty_by_product_id is already built above — reused here to ensure
    # the check and the debit operate on identical aggregated values.

    ProductModel.objects.filter(
        pk__in=list(qty_by_product_id.keys())
    ).update(
        quantity=Case(
            *[
                When(pk=pk, then=F('quantity') - total_qty)
                for pk, total_qty in qty_by_product_id.items()
            ],
            output_field=IntegerField(),
        )
    )

    logger.info(
        'order_created id=%s phone=%s items=%d total=%s',
        order.pk, order.phone_number, len(to_create), order.total_price,
    )
    return order
