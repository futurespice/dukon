import logging

from django.db import transaction
from django.db.models import Q
from django.db.utils import IntegrityError, DataError

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import UserRateThrottle

from apps.common.permissions import IsVerifiedUser
from apps.common.mixins import validate_bulk_ids
from apps.orders.models import Order
from apps.orders.serializers import (
    OrderSerializer, OrderUpdateSerializer, OrderListSerializer,
    OrderTrackSerializer, OrderCheckPhotoSerializer,
)
from apps.orders.services import cancel_order, restore_stock_for_order_items
from apps.orders.filters import OrderFilter
from apps.accounts.throttles import VerifyCodeThrottle, OrderTrackThrottle

logger = logging.getLogger(__name__)


class CreateOrderThrottle(UserRateThrottle):
    rate = '30/hour'


# ---------------------------------------------------------------------------
# Base querysets
# ---------------------------------------------------------------------------

# AUDIT-3 FIX #1, #9: Removed _db_total_price annotation.
# The annotation produced wrong totals when combined with .filter(items__...).distinct()
# because Sum() runs over the JOIN rows BEFORE DISTINCT. prefetch_related already
# loads items into cache, so obj.total_price (a Python property) uses that cache
# with zero extra SQL queries.
_ORDER_QS = Order.objects.select_related('user').prefetch_related(
    'items__product__photos__image',
    'items__product__product__store',
)


def _store_owner_qs(user):
    """Orders that belong to the user's stores (store-owner perspective)."""
    if user.is_staff:
        return _ORDER_QS.all()
    return _ORDER_QS.filter(
        items__product__product__store__admin_user=user
    ).distinct()


def _owner_qs(user):
    """Orders visible to an authenticated user: own purchases OR orders from their stores."""
    if user.is_staff:
        return _ORDER_QS.all()
    return _ORDER_QS.filter(
        Q(user=user) |
        Q(items__product__product__store__admin_user=user)
    ).distinct()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class OrderListCreateView(generics.ListCreateAPIView):
    """
    POST /orders/  — create order (IsVerifiedUser, user set from request).
    GET  /orders/  — store-owner view: orders containing products from the user's stores.
    """
    filterset_class = OrderFilter
    search_fields = ('phone_number', 'first_name', 'last_name', 'address')
    ordering_fields = ('created_at',)

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Order.objects.none()
        return _store_owner_qs(user)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return OrderSerializer
        return OrderListSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsVerifiedUser()]
        return [IsAuthenticated()]

    def get_throttles(self):
        if self.request.method == 'POST':
            return [CreateOrderThrottle()]
        return []

    def post(self, request, *args, **kwargs):
        idempotency_key = request.headers.get('Idempotency-Key')
        if idempotency_key and request.user.is_authenticated:
            # Idempotency check: if an order with this key already exists for the user,
            # return it with 200 OK instead of creating a duplicate.
            existing_order = Order.objects.filter(
                user=request.user,
                idempotency_key=idempotency_key
            ).first()
            if existing_order:
                serializer = self.get_serializer(existing_order)
                return Response(serializer.data, status=status.HTTP_200_OK)

        try:
            return super().post(request, *args, **kwargs)
        except IntegrityError:
            # CRITICAL-2 FIX (Idempotency Race → Double Order):
            # Race scenario:
            #   T1: Req-A & Req-B both read idempotency check → None (A not yet committed)
            #   T2: Req-A creates Order #1 & commits
            #   T3: Req-B hits IntegrityError on idempotency_key UNIQUE constraint
            # If we return 409 here, the client may retry WITHOUT the key and
            # create Order #2 → double stock decrement.
            #
            # Fix: on IntegrityError, check whether this specific idempotency_key
            # already produced an order. If yes → return it with 200 OK (safe retry).
            # If no → it's a genuine DB error (e.g. stock constraint) → return 409.
            if idempotency_key and request.user.is_authenticated:
                existing_order = Order.objects.filter(
                    user=request.user,
                    idempotency_key=idempotency_key,
                ).first()
                if existing_order:
                    serializer = OrderListSerializer(
                        existing_order, context={'request': request}
                    )
                    return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(
                {'detail': 'Операция отклонена базой данных (нарушение уникальности или отказ по остаткам).'},
                status=status.HTTP_409_CONFLICT,
            )

    def perform_create(self, serializer):
        idempotency_key = self.request.headers.get('Idempotency-Key')
        serializer.save(user=self.request.user, idempotency_key=idempotency_key)


class OrderGetMultipleView(generics.ListAPIView):
    """Store owner: all orders that contain products from their stores."""
    serializer_class = OrderListSerializer
    filterset_class = OrderFilter
    search_fields = ('phone_number', 'first_name', 'last_name')
    ordering_fields = ('created_at',)
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return _store_owner_qs(self.request.user)


class OrderMyListView(generics.ListAPIView):
    """GET /orders/my/ — authenticated client's own purchase history."""
    serializer_class = OrderListSerializer
    filterset_class = OrderFilter
    search_fields = ('phone_number', 'first_name', 'last_name')
    ordering_fields = ('created_at',)
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return _ORDER_QS.filter(user=self.request.user)


class OrderHistoryListView(OrderMyListView):
    """Backward-compatible alias for /orders/my/."""
    pass


class OrderTrackView(APIView):
    """
    GET /orders/track/?order_id=42&phone=+996555123456
    Public endpoint for guest order tracking.
    Returns only status fields — no user data, no pricing details.
    Throttled per (IP, order_id) to prevent order ID enumeration.
    """
    permission_classes = (AllowAny,)
    # R-3 FIX: OrderTrackThrottle keys by (IP + order_id), not just IP.
    # This limits probing a single order from one IP without restricting
    # legitimate users who look up different orders.
    throttle_classes = (OrderTrackThrottle,)

    def get(self, request):
        order_id_raw = request.query_params.get('order_id')
        phone = request.query_params.get('phone')

        if not order_id_raw or not phone:
            return Response(
                {'detail': 'Параметры order_id и phone обязательны.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order_id = int(order_id_raw)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'order_id должен быть числом.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.accounts.services import normalize_phone
        try:
            phone = normalize_phone(phone)
        except ValueError:
            return Response(
                {'detail': 'Неверный формат номера телефона.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = Order.objects.only(
                'id', 'order_status', 'delivery_status', 'payment_status',
                'created_at', 'updated_at', 'first_name', 'last_name',
                'delivery_type', 'payment_type',
            ).get(pk=order_id, phone_number=phone)
        except Order.DoesNotExist:
            return Response(
                {'detail': 'Заказ не найден. Проверьте номер заказа и телефон.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (OverflowError, DataError):
            # Fintech Fail-Safe: prevents 500 when order_id exceeds BIGINT bounds for the DB.
            return Response(
                {'detail': 'Номер заказа содержит недопустимое значение.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(OrderTrackSerializer(order).data, status=status.HTTP_200_OK)


class OrderMultipleDeleteView(APIView):
    """
    Soft delete: marks orders as CANCELED instead of physically removing them.

    FIX #1 (CRITICAL — Race Condition):
    Previously orders_to_cancel was read without row-level locking, creating a
    TOCTOU window: two concurrent POSTs with overlapping IDs could both read
    the same orders as cancellable, both restore stock, and both call qs.update().
    Result: double stock restoration (warehouse inventory inflated).

    Fix: select_for_update(skip_locked=True) acquires row-level locks before
    reading. skip_locked=True means a second concurrent request simply skips
    already-locked orders rather than waiting — safe and deadlock-free.

    FIX #5 (DRY): restore_stock_for_order_items() and cancel_order() logic
    moved to orders.services. Views no longer import ProductModel or F().
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data, action='отменить')
        if err:
            return err

        user = request.user
        cancellable_statuses = [
            Order.OrderStatus.IN_PROCESSING,
            Order.OrderStatus.ACCEPTED,
        ]

        if user.is_staff:
            qs = Order.objects.filter(pk__in=ids, order_status__in=cancellable_statuses)
        else:
            qs = Order.objects.filter(
                pk__in=ids,
                order_status__in=cancellable_statuses,
                items__product__product__store__admin_user=user,
            ).distinct()

        with transaction.atomic():
            # FIX #1: Lock rows before reading to prevent concurrent double-cancel.
            # skip_locked=True avoids blocking if another request already holds a lock.
            #
            # M-6 FIX: prefetch_related() on a select_for_update() queryset locks
            # the Order rows but NOT the prefetched OrderItem rows. Reading items
            # from the prefetch cache is safe here because:
            #   a) F()-based stock updates in restore_stock_for_order_items() are
            #      atomic at the DB level regardless of whether we hold an OrderItem lock.
            #   b) The Order row itself IS locked (skip_locked=True), so no concurrent
            #      request can cancel the same order and duplicate the restoration.
            # We explicitly use .select_related() on the items queryset to ensure
            # product_id is available without a second per-item SELECT.
            orders_to_cancel = list(
                qs.select_for_update(skip_locked=True).prefetch_related('items')
            )

            for order in orders_to_cancel:
                # Pass items from prefetch cache — safe because Order is locked above.
                restore_stock_for_order_items(order.items.all())

            # Bulk-cancel only the rows we actually locked (skip_locked may have
            # excluded some rows that were being processed concurrently).
            locked_ids = [o.pk for o in orders_to_cancel]
            canceled_count = Order.objects.filter(
                pk__in=locked_ids
            ).update(order_status=Order.OrderStatus.CANCELED)

        logger.info(
            'orders_bulk_canceled ids=%s locked=%s count=%d by_user=%s',
            ids, locked_ids, canceled_count, user.pk,
        )
        return Response({'canceled': canceled_count}, status=status.HTTP_200_OK)


class OrderUploadCheckView(APIView):
    """
    PATCH /orders/{id}/upload-check/
    Allows the buyer to upload a payment screenshot (check_photo) for their order.
    """
    permission_classes = (IsVerifiedUser,)

    def get_parsers(self):
        from rest_framework.parsers import MultiPartParser, FormParser
        return [MultiPartParser(), FormParser()]

    def patch(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({'detail': 'Заказ не найден.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrderCheckPhotoSerializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET:        _owner_qs — buyers see their own orders, store owners see store orders.
    PUT/PATCH:  restricted to store-owner orders only.
    DELETE:     soft-delete via cancel_order() service — sets CANCELED, returns updated object.
    """
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _owner_qs(user)
        return _store_owner_qs(user)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return OrderListSerializer
        return OrderUpdateSerializer

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete: mark as CANCELED instead of removing the row.
        Returns the updated order object so the client immediately sees
        the new status without a follow-up GET.

        FIX #5 (DRY): delegates stock restoration to cancel_order() service.
        """
        order = self.get_object()

        cancellable = {
            Order.OrderStatus.IN_PROCESSING,
            Order.OrderStatus.ACCEPTED,
        }
        if order.order_status not in cancellable:
            return Response(
                {'detail': f'Невозможно отменить заказ в статусе «{order.get_order_status_display()}».'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # cancel_order() is itself decorated with @transaction.atomic.
        cancel_order(order)

        logger.info('order_canceled id=%s by_user=%s', order.pk, request.user.pk)
        order.refresh_from_db()
        return Response(
            OrderListSerializer(order, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )
