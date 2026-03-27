import logging

from django.db import transaction
from django.db.models import F

from rest_framework import serializers

from apps.common.mixins import PhoneNormalizeMixin
from apps.orders.models import Order, OrderItem
from apps.products.models import ProductModel
from apps.products.serializers import ProductModelListSerializer
from apps.orders.services import (
    create_order as _create_order_service,
    restore_stock_for_order_items,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight user representation for order lists.
# ---------------------------------------------------------------------------

class OrderUserSerializer(serializers.Serializer):
    """Minimal buyer data embedded inside order list responses."""
    id = serializers.IntegerField(read_only=True)
    phone = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)

    def to_representation(self, instance):
        if instance is None:
            return None
        return super().to_representation(instance)


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer used for creating order items. Validates quantity and stock."""
    order = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            'id', 'created_at', 'updated_at',
            'quantity', 'order', 'product',
            'price_at_order', 'product_name_at_order',
        )
        read_only_fields = (
            'id', 'created_at', 'updated_at', 'order',
            'price_at_order', 'product_name_at_order',
        )

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('Количество должно быть не менее 1.')
        if value > 9999:
            raise serializers.ValidationError('Количество не может превышать 9999.')
        return value

    def validate(self, attrs):
        """Pre-flight stock check (no lock). Authoritative locked check runs in create()."""
        product: ProductModel = attrs.get('product')
        quantity: int = attrs.get('quantity', 1)
        if product and product.quantity < quantity:
            raise serializers.ValidationError(
                f'Недостаточно товара на складе. '
                f'Запрошено: {quantity}, доступно: {product.quantity}.'
            )
        return attrs


class OrderItemListSerializer(serializers.ModelSerializer):
    """Read-only serializer that exposes full product details."""
    product = ProductModelListSerializer(read_only=True)
    order = serializers.PrimaryKeyRelatedField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            'id', 'product', 'created_at', 'updated_at',
            'quantity', 'order',
            'price_at_order', 'product_name_at_order', 'subtotal',
        )
        read_only_fields = (
            'id', 'created_at', 'updated_at', 'order',
            'price_at_order', 'product_name_at_order', 'subtotal',
        )


class OrderSerializer(PhoneNormalizeMixin, serializers.ModelSerializer):
    """Create serializer. Validates phone, address conditionality, and stock."""
    items = OrderItemSerializer(many=True)
    total_price = serializers.SerializerMethodField()

    address = serializers.CharField(max_length=250, allow_blank=True, default='')

    class Meta:
        model = Order
        fields = (
            'id', 'items', 'total_price', 'created_at', 'updated_at',
            'notifications_sent', 'phone_number', 'first_name', 'last_name',
            'comment', 'address', 'payment_type', 'delivery_type',
            'order_status', 'delivery_status', 'payment_status', 'check_photo',
        )
        read_only_fields = (
            'id', 'created_at', 'updated_at',
            'order_status', 'delivery_status', 'payment_status', 'check_photo',
            'total_price',
            # notifications_sent must be read_only on create — a guest passing
            # "notifications_sent": true would suppress delivery notifications.
            'notifications_sent',
        )

    def get_total_price(self, obj):
        return obj.total_price

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('Заказ должен содержать хотя бы одну позицию.')
        # FIX (data integrity + negative stock prevention):
        # Duplicate product_id entries in a CREATE request create multiple
        # OrderItem rows for the same product in one order, which is
        # inconsistent data (the UI would show the same product twice).
        # create_order() aggregates qty correctly so stock math holds, but
        # the duplicate OrderItem rows break order history and total_price
        # display. Reject at the validation layer.
        pids = [item['product'].pk for item in value]
        if len(pids) != len(set(pids)):
            raise serializers.ValidationError(
                'Список позиций содержит дублирующиеся товары. '
                'Укажите каждый товар не более одного раза.'
            )
        return value

    def validate(self, attrs):
        delivery_type = attrs.get('delivery_type', Order.DeliveryType.SELF_PICKUP)
        address = attrs.get('address', '').strip()
        if delivery_type == Order.DeliveryType.DELIVERY and not address:
            raise serializers.ValidationError(
                {'address': 'Адрес обязателен при выборе типа доставки «Доставка».'}
            )
        return attrs

    def create(self, validated_data):
        """
        A-3 REFACTOR: delegates all stock-locking, item creation, and
        inventory decrement logic to orders.services.create_order().

        The serializer retains responsibility for:
          - input validation (validate_items, validate)
          - injecting request.user (done by perform_create in the view)
        All DB operations live in the service layer for testability.
        """
        return _create_order_service(validated_data)


# ---------------------------------------------------------------------------
# Order status state machine
# ---------------------------------------------------------------------------

# Terminal states: once an order reaches one of these, its stock has already
# been either restored (CANCELED) or never needs restoration (REJECTED via
# the PATCH path which now restores stock too — see update() below).
# This set is used in two places:
#   1. was_terminal_reached guard in update() to trigger stock restoration.
#   2. items_data guard to block item mutations on a closed order.
_ORDER_TERMINAL_STATES: frozenset = frozenset({
    Order.OrderStatus.CANCELED,
    Order.OrderStatus.REJECTED,
})

_ALLOWED_ORDER_STATUS_TRANSITIONS = {
    Order.OrderStatus.IN_PROCESSING: {
        Order.OrderStatus.ACCEPTED,
        Order.OrderStatus.CANCELED,
        Order.OrderStatus.REJECTED,
    },
    Order.OrderStatus.ACCEPTED: {Order.OrderStatus.CANCELED, Order.OrderStatus.REJECTED},
    Order.OrderStatus.CANCELED: set(),
    Order.OrderStatus.REJECTED: set(),
}
_ALLOWED_DELIVERY_STATUS_TRANSITIONS = {
    Order.DeliveryStatus.IN_PROCESSING: {
        Order.DeliveryStatus.IN_PROGRESS,
        Order.DeliveryStatus.CANCELED,
        Order.DeliveryStatus.REJECTED,
    },
    Order.DeliveryStatus.IN_PROGRESS: {
        Order.DeliveryStatus.DELIVERED,
        Order.DeliveryStatus.CANCELED,
        Order.DeliveryStatus.RETURNED,
    },
    Order.DeliveryStatus.DELIVERED: {Order.DeliveryStatus.RETURNED},
    Order.DeliveryStatus.CANCELED: set(),
    Order.DeliveryStatus.RETURNED: set(),
    Order.DeliveryStatus.REJECTED: set(),
}
_ALLOWED_PAYMENT_STATUS_TRANSITIONS = {
    Order.PaymentStatus.WAITING_FOR_PAY: {Order.PaymentStatus.PAID},
    Order.PaymentStatus.PAID: {Order.PaymentStatus.REFUNDED},
    Order.PaymentStatus.REFUNDED: set(),
}


class OrderUpdateSerializer(PhoneNormalizeMixin, serializers.ModelSerializer):
    """
    Update serializer. Items updated in-place preserving IDs.

    FIX #3 (CRITICAL — Race Condition on existing items):
    Previously existing OrderItems were read without row-level locking.
    A concurrent request modifying the same order's items could cause
    old_qty to be stale → diff calculation wrong → stock corrupted.

    Fix: select_for_update() is now applied to ALL items being processed:
      - Existing items: locked via instance.items.select_for_update()
      - New product stock: locked via ProductModel.objects.select_for_update()
    Both locks use sorted PKs to prevent deadlocks.
    """
    items = OrderItemSerializer(many=True, required=False)

    class Meta:
        model = Order
        fields = (
            'id', 'items', 'created_at', 'updated_at',
            'notifications_sent', 'phone_number', 'first_name', 'last_name',
            'comment', 'address', 'payment_type', 'delivery_type',
            'order_status', 'delivery_status', 'payment_status', 'check_photo',
        )
        # notifications_sent is read_only — prevents store owners from manually
        # setting it to True and suppressing delivery notifications.
        # check_photo is NOT read_only here — store owner can upload a receipt scan.
        read_only_fields = ('id', 'created_at', 'updated_at', 'notifications_sent')

    def validate_items(self, value):
        if value is None:
            return value
        if len(value) == 0:
            raise serializers.ValidationError(
                'Нельзя передать пустой список позиций. '
                'Не передавайте поле items, если не хотите его менять.'
            )
        # FIX (CRITICAL — negative stock via in-memory mutation of old_qty):
        # If items_data contains two entries for the same existing product_id,
        # Pass 4 of update() mutates existing_item.quantity in-memory after the
        # first iteration, so the second iteration computes a WRONG diff against
        # the already-updated in-memory value. This produces a second F()-based
        # UPDATE that pushes stock negative without triggering the stock check.
        #
        # Example: existing qty=3, items=[{P5,qty:5},{P5,qty:8}], stock=3.
        # Pass 3 validates diff=5-3=2, stock(3)>=2 → OK.
        # Pass 4 iter 1: UPDATE quantity-=2, existing_item.quantity=5 (in-memory).
        # Pass 4 iter 2: old_qty=5 (mutated!), diff=8-5=3, UPDATE quantity-=3.
        # Net deduction: 2+3=5, stock=3-5=-2. NEGATIVE.
        #
        # Reject at validation layer: any product_id must appear at most once.
        pids = [item['product'].pk for item in value]
        if len(pids) != len(set(pids)):
            raise serializers.ValidationError(
                'Список позиций содержит дублирующиеся товары. '
                'Укажите каждый товар не более одного раза.'
            )
        return value

    def _validate_status_transition(self, allowed_map, current, new, label):
        """
        Pure state-machine check: is `new` reachable from `current`?
        Used both in pre-flight validation (stale) and in the authoritative
        locked re-check inside update().
        """
        if new == current:
            return new
        allowed = allowed_map.get(current, set())
        if new not in allowed:
            raise serializers.ValidationError(
                f'Переход {label} из «{current}» в «{new}» запрещён.'
            )
        return new

    # ------------------------------------------------------------------
    # Pre-flight validators (use self.instance — stale, no DB lock).
    # Purpose: give the client a fast 400 response for obviously illegal
    # inputs WITHOUT acquiring any DB locks yet. These are an optimistic
    # UX shortcut only — they do NOT guarantee correctness under concurrency.
    # The authoritative check runs inside update() on the locked row.
    # ------------------------------------------------------------------

    def validate_order_status(self, value):
        if self.instance:
            return self._validate_status_transition(
                _ALLOWED_ORDER_STATUS_TRANSITIONS,
                self.instance.order_status, value, 'статуса заказа',
            )
        return value

    def validate_delivery_status(self, value):
        if self.instance:
            return self._validate_status_transition(
                _ALLOWED_DELIVERY_STATUS_TRANSITIONS,
                self.instance.delivery_status, value, 'статуса доставки',
            )
        return value

    def validate_payment_status(self, value):
        if self.instance:
            return self._validate_status_transition(
                _ALLOWED_PAYMENT_STATUS_TRANSITIONS,
                self.instance.payment_status, value, 'статуса оплаты',
            )
        return value

    def _recheck_status_transitions_locked(self, locked_instance, validated_data):
        """
        AUTHORITATIVE state-machine enforcement executed AFTER acquiring the
        row-level lock on the Order row inside update().

        WHY THIS EXISTS (C-NEW-1 FIX):
        DRF's validate_*() methods run on self.instance which was fetched by
        get_object() WITHOUT a lock, potentially many milliseconds before
        update() acquires select_for_update(). Between those two moments a
        concurrent request may have committed a status change, making the
        pre-flight validation result invalid:

          T0: order.order_status = ACCEPTED  (in DB)
          T1: Request A validates ACCEPTED→REJECTED ✓  (stale read)
          T2: Request B validates ACCEPTED→CANCELED ✓  (stale read)
          T3: Request B locks & saves → order.order_status = CANCELED
          T4: Request A locks, sees CANCELED (terminal), but validated_data
              already carries order_status=REJECTED → setattr would write
              REJECTED onto a CANCELED order, bypassing the state machine
              and corrupting stock (stock was already restored at T3).

        This method re-runs the same state-machine check using the fresh
        locked_instance values. Because it runs BEFORE any setattr/save,
        it atomically blocks the invalid transition and rolls back.

        Args:
            locked_instance: Order row fetched with select_for_update().
            validated_data:  dict of fields that passed pre-flight validation.

        Raises:
            serializers.ValidationError — if a transition is now illegal
            given the locked (actual current) state of the order.
        """
        checks = [
            (
                'order_status',
                _ALLOWED_ORDER_STATUS_TRANSITIONS,
                locked_instance.order_status,
                'статуса заказа',
            ),
            (
                'delivery_status',
                _ALLOWED_DELIVERY_STATUS_TRANSITIONS,
                locked_instance.delivery_status,
                'статуса доставки',
            ),
            (
                'payment_status',
                _ALLOWED_PAYMENT_STATUS_TRANSITIONS,
                locked_instance.payment_status,
                'статуса оплаты',
            ),
        ]
        errors = {}
        for field, allowed_map, current_locked, label in checks:
            new_value = validated_data.get(field)
            if new_value is None or new_value == current_locked:
                continue
            allowed = allowed_map.get(current_locked, set())
            if new_value not in allowed:
                # The status changed between pre-flight validation and the
                # lock acquisition — this transition is now forbidden.
                errors[field] = (
                    f'Переход {label} из «{current_locked}» в «{new_value}» запрещён. '
                    f'Статус был изменён параллельным запросом.'
                )
        if errors:
            raise serializers.ValidationError(errors)

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)

        # C-2 FIX: re-fetch with a row-level lock so that only one concurrent
        # request mutates this order at a time. All subsequent reads/writes
        # within this atomic block see the committed, current state.
        locked_instance = Order.objects.select_for_update().get(pk=instance.pk)

        # C-NEW-1 FIX (CRITICAL — State Machine Bypass under Concurrency):
        # Re-validate ALL status transitions against the LOCKED instance
        # BEFORE applying any changes. This is the authoritative enforcement
        # point — see _recheck_status_transitions_locked() docstring for the
        # full race-condition scenario this prevents.
        self._recheck_status_transitions_locked(locked_instance, validated_data)

        new_order_status = validated_data.get('order_status')

        # FIX (CRITICAL — stock not restored on REJECTED transition):
        # The original code only restored stock when transitioning to CANCELED.
        # A PATCH that sets order_status=REJECTED left inventory permanently
        # decremented: the items were never fulfilled, but stock was never
        # returned. The cancel_order() terminal guard then blocked all future
        # restoration attempts on the already-REJECTED order.
        #
        # Fix: treat both CANCELED and REJECTED as terminal states that trigger
        # stock restoration. was_terminal_reached is True when we are moving
        # INTO a terminal state from a non-terminal state (i.e., first time).
        was_terminal_reached = (
            new_order_status in _ORDER_TERMINAL_STATES
            and locked_instance.order_status not in _ORDER_TERMINAL_STATES
        )

        for attr, value in validated_data.items():
            setattr(locked_instance, attr, value)
        locked_instance.save()

        if was_terminal_reached:
            # Terminal state reached — restore stock and exit early.
            # Early return prevents double-adjustment if items_data was also
            # provided alongside the status change (restore-all + per-item
            # diff would produce wrong totals).
            restore_stock_for_order_items(locked_instance.items.all())
            return locked_instance

        if items_data is not None:
            # FIX (HIGH — item mutations on already-terminal orders):
            # If the order was ALREADY in a terminal state BEFORE this request
            # (i.e., no status transition is being requested now), and the
            # client sends items_data, we must refuse. The stock was already
            # restored when the order became terminal; processing items again
            # would re-deduct or double-restore inventory.
            if locked_instance.order_status in _ORDER_TERMINAL_STATES:
                raise serializers.ValidationError({
                    'items': (
                        f'Нельзя изменять позиции заказа в статусе '
                        f'«{locked_instance.get_order_status_display()}».'
                    )
                })
            # Lock ALL existing OrderItem rows before reading their quantities.
            # Sorted PKs prevent deadlocks with concurrent transactions.
            existing = {
                item.product_id: item
                for item in locked_instance.items.select_for_update().order_by('product_id')
            }
            incoming_product_ids = set()

            # -------------------------------------------------------------------
            # C-2 FIX (CRITICAL — Negative stock via duplicate new product_ids):
            # Per-item stock checks let duplicates slip through:
            #   stock=4, items=[{pid:5,qty:3},{pid:5,qty:3}]
            #   per-item: 4>=3 ✓, 4>=3 ✓  → no error
            #   deduction: 4-3=1, then 1-3=-2  → NEGATIVE STOCK
            # Fix: aggregate total demanded qty per new product_id first;
            # check the SUM against the locked stock value.
            #
            # C-3 FIX (CRITICAL — Deadlock on parallel PATCH requests):
            # Previously existing items with diff>0 were locked one-by-one
            # inside the loop in client-controlled (arbitrary) order:
            #   Req A: locks P5 → waits for P6
            #   Req B: locks P6 → waits for P5  → DEADLOCK
            # Fix: gather ALL product_ids that need a row-level lock (new
            # products + existing items with qty increase), sort them once,
            # and acquire ALL locks in a SINGLE query. Consistent sorted order
            # across all concurrent transactions eliminates the deadlock.
            # -------------------------------------------------------------------

            # Pass 1: classify each item_data and compute aggregates.
            new_qty_by_pid: dict[int, int] = {}       # new products: aggregated qty
            existing_inc_pids: set[int] = set()       # existing pids with qty increase

            for item_data in items_data:
                pid = item_data['product'].pk
                qty = item_data['quantity']
                incoming_product_ids.add(pid)
                if pid in existing:
                    if qty > existing[pid].quantity:
                        existing_inc_pids.add(pid)
                else:
                    new_qty_by_pid[pid] = new_qty_by_pid.get(pid, 0) + qty

            # Pass 2: acquire ALL required product locks in ONE sorted query.
            # select_related('product') avoids N+1 when reading product.name
            # in Pass 3 error messages and Pass 4 price/name snapshots.
            pids_to_lock = sorted(set(new_qty_by_pid.keys()) | existing_inc_pids)
            locked_products: dict[int, 'ProductModel'] = {}
            if pids_to_lock:
                locked_products = {
                    p.pk: p
                    for p in ProductModel.objects.select_for_update().select_related(
                        'product'
                    ).filter(
                        pk__in=pids_to_lock
                    )
                }

            # Pass 3: validate stock against locked rows — fail fast before mutations.
            stock_errors = []
            for pid, total_qty in new_qty_by_pid.items():
                lp = locked_products.get(pid)
                if lp and lp.quantity < total_qty:
                    stock_errors.append(
                        f'Товар «{lp.product.name} — {lp.name}»: '
                        f'запрошено {total_qty}, доступно {lp.quantity}.'
                    )
            for pid in existing_inc_pids:
                lp = locked_products.get(pid)
                if lp:
                    diff = next(
                        (d['quantity'] for d in items_data if d['product'].pk == pid),
                        existing[pid].quantity,
                    ) - existing[pid].quantity
                    if lp.quantity < diff:
                        stock_errors.append(
                            f'Товар «{lp.product.name} — {lp.name}»: '
                            f'запрошено увеличение на {diff}, '
                            f'доступно {lp.quantity}.'
                        )
            if stock_errors:
                raise serializers.ValidationError({'items': stock_errors})

            # Pass 4: apply mutations.
            items_to_bulk_update = []
            processed_new_pids: set[int] = set()

            for item_data in items_data:
                product: ProductModel = item_data['product']
                pid = product.pk

                if pid in existing:
                    existing_item = existing[pid]
                    old_qty = existing_item.quantity
                    new_qty = item_data['quantity']
                    if old_qty != new_qty:
                        diff = new_qty - old_qty
                        # diff > 0 → reduce stock (validated above against locked row);
                        # diff < 0 → restore stock (always safe, no lock needed).
                        ProductModel.objects.filter(pk=pid).update(
                            quantity=F('quantity') - diff
                        )
                    existing_item.quantity = new_qty
                    items_to_bulk_update.append(existing_item)
                else:
                    if pid in processed_new_pids:
                        # C-2 FIX: duplicate new product_id in items_data —
                        # the aggregated OrderItem was already created on the
                        # first encounter. Skip to avoid double-create/deduct.
                        continue
                    processed_new_pids.add(pid)
                    total_qty = new_qty_by_pid[pid]
                    # CRITICAL-3 FIX (Stale price/name on new OrderItems):
                    # `product` here is item_data['product'] — the instance
                    # deserialized at validation time, BEFORE the transaction
                    # and BEFORE select_for_update(). Its .price and .name may
                    # already be outdated if an admin changed them concurrently.
                    # locked_products[pid] is fetched inside the transaction
                    # with select_for_update() — it reflects the committed,
                    # authoritative state of the product row.
                    # Always use the locked instance for price/name snapshots.
                    locked_product = locked_products[pid]
                    OrderItem.objects.create(
                        order=locked_instance,
                        product=locked_product,
                        quantity=total_qty,
                        price_at_order=locked_product.price,
                        product_name_at_order=(
                            f'{locked_product.product.name} — {locked_product.name}'
                        ),
                    )
                    ProductModel.objects.filter(pk=pid).update(
                        quantity=F('quantity') - total_qty
                    )

            if items_to_bulk_update:
                OrderItem.objects.bulk_update(items_to_bulk_update, ['quantity'])

            # Restore stock for removed items and delete their rows.
            to_delete_pks = [pk for pk in existing if pk not in incoming_product_ids]
            if to_delete_pks:
                for pk in to_delete_pks:
                    removed_item = existing[pk]
                    if removed_item.product_id:
                        ProductModel.objects.filter(pk=removed_item.product_id).update(
                            quantity=F('quantity') + removed_item.quantity
                        )
                locked_instance.items.filter(product_id__in=to_delete_pks).delete()

        return locked_instance


class OrderListSerializer(serializers.ModelSerializer):
    """Read serializer with nested data. Uses lightweight user serializer."""
    items = serializers.SerializerMethodField()
    user = OrderUserSerializer(read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 'items', 'user', 'total_price', 'created_at', 'updated_at',
            'notifications_sent', 'phone_number', 'first_name', 'last_name',
            'comment', 'address', 'payment_type', 'delivery_type',
            'order_status', 'delivery_status', 'payment_status', 'check_photo',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'total_price')

    def get_items(self, obj):
        """
        Filter order items so store owners only see items belonging to their stores.
        Buyers and staff see all items.

        Uses Python-level filtering on the prefetch cache instead of .filter()
        which would break prefetch and cause N+1 queries.
        """
        request = self.context.get('request')
        items = list(obj.items.all())  # uses prefetch cache
        if request and request.user.is_authenticated and not request.user.is_staff:
            if obj.user_id and obj.user_id == request.user.pk:
                pass  # buyer sees all their own order items
            else:
                # Store owner — filter in Python to preserve prefetch cache.
                items = [
                    item for item in items
                    if item.product
                    and item.product.product
                    and item.product.product.store
                    and item.product.product.store.admin_user_id == request.user.pk
                ]
        return OrderItemListSerializer(items, many=True).data

    def get_total_price(self, obj):
        # Always use obj.total_price which reads from prefetch cache.
        return obj.total_price


class OrderCheckPhotoSerializer(serializers.ModelSerializer):
    """Allows the buyer to upload a payment screenshot for their order."""

    class Meta:
        model = Order
        fields = ('id', 'check_photo')
        read_only_fields = ('id',)

    def validate_check_photo(self, value):
        if value is None:
            return value
        # CRITICAL-4 FIX (MIME Spoofing — no PIL validation):
        # The original implementation only checked the HTTP Content-Type header,
        # which is fully controlled by the client. An attacker could upload any
        # file (PHP, EXE, SVG with XSS) by setting Content-Type: image/jpeg.
        # All other upload endpoints in this project use validate_image_upload()
        # which additionally runs PIL magic-bytes verification to confirm the
        # actual file content matches an allowed image format.
        # Fix: replace the ad-hoc check with the shared validator. The limit is
        # 10 MB (matching the original) vs the 5 MB default — passed explicitly.
        from apps.common.validators import validate_image_upload
        return validate_image_upload(value, max_mb=10, field_label='check_photo')


class OrderTrackSerializer(serializers.ModelSerializer):
    """
    Public read-only serializer for guest order tracking.
    Exposes only status fields — no user data, no pricing, no items details.
    """

    class Meta:
        model = Order
        fields = (
            'id', 'created_at', 'updated_at',
            'order_status', 'delivery_status', 'payment_status',
            'delivery_type', 'payment_type',
        )
        read_only_fields = (
            'id', 'created_at', 'updated_at',
            'order_status', 'delivery_status', 'payment_status',
            'delivery_type', 'payment_type',
        )
