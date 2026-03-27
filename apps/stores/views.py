import logging

from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404

from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.common.constants import MAX_BULK_OPERATIONS
from apps.common.permissions import IsStoreOwner, IsVerifiedUser
from apps.common.mixins import validate_bulk_ids
from apps.stores.models import (
    Store, StorePhoto, BankType, StoreBankDetail,
    StoreBalanceTransaction, StoreTariffPlan, Slide,
)
from apps.stores.serializers import (
    StoreSerializer, StoreOwnerSerializer,
    StorePhotoSerializer, StorePhotoCreateSerializer,
    BankTypeSerializer,
    StoreBankDetailSerializer, StoreBankDetailListSerializer,
    StoreBalanceTransactionSerializer, StoreBalanceTransactionListSerializer,
    StoreTariffPlanSerializer, StoreTariffPlanCreateSerializer,
    SlideSerializer,
    ToActivatePromocodeSerializer,
)
from apps.stores.services import (
    purchase_tariff, TariffError,
    activate_promocode, PromocodeError,
    check_slide_limit,
    create_slide_locked,
    reorder_slides,
    TARIFF_PRICES,
)
from apps.stores.filters import (
    StoreFilter, StorePhotoFilter,
    StoreBalanceTransactionFilter, SlideFilter,
    StoreBankDetailFilter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

class StoreListCreateView(generics.ListCreateAPIView):
    queryset = Store.objects.select_related('region', 'admin_user').prefetch_related('photos', 'slides')
    filterset_class = StoreFilter
    search_fields = ('name', 'address', 'slug')
    ordering_fields = ('name', 'created_at')

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return StoreSerializer
        return StoreOwnerSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsVerifiedUser()]

    def perform_create(self, serializer):
        serializer.save(admin_user=self.request.user)


class StoreGetMultipleView(generics.ListAPIView):
    queryset = Store.objects.select_related('region', 'admin_user').prefetch_related('photos', 'slides')
    serializer_class = StoreSerializer
    permission_classes = (AllowAny,)
    filterset_class = StoreFilter
    search_fields = ('name', 'address', 'slug')


class StoreMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err

        from apps.orders.models import Order

        # M-1 FIX (TOCTOU — active-order check races with delete):
        # Original code ran the active-orders check and the DELETE in two
        # separate transactions. A new order placed between them would be
        # orphaned by the cascade: Store → Products → ProductModel →
        # OrderItem (SET_NULL) → order items lose their product reference.
        #
        # Fix: wrap both the guard-check AND the DELETE in one atomic block,
        # with select_for_update() locking the store rows first. Any
        # concurrent transaction that touches these stores (e.g. an order
        # creation that joins through products) will block until we commit,
        # ensuring the guard and the delete see consistent state.
        with transaction.atomic():
            # Lock the exact stores we intend to delete.  skip_locked=False
            # (default) means we WAIT for any concurrent lock rather than
            # silently skipping — correct here because we need to know the
            # full set of stores before deciding to proceed.
            # CRITICAL-1 FIX (Deadlock Prevention):
            # select_for_update() without order_by() acquires row-level locks
            # in an arbitrary DB order. Two concurrent requests with overlapping
            # UUIDs can each lock rows in opposite order → DEADLOCK.
            # Fix: sort by UUID so ALL transactions acquire locks in the same
            # deterministic order, eliminating the circular-wait condition.
            candidate_stores = list(
                Store.objects
                .select_for_update()
                .filter(uuid__in=ids, admin_user=request.user)
                .order_by('uuid')
            )
            if not candidate_stores:
                return Response({'deleted': 0}, status=status.HTTP_200_OK)

            candidate_uuids = [s.uuid for s in candidate_stores]

            # Re-check for active orders INSIDE the transaction so the
            # guard and the delete are atomic — no new order can slip in
            # after this check because the store rows are now locked.
            active_store_names = list(
                Store.objects
                .filter(
                    uuid__in=candidate_uuids,
                    products__models__order_items__order__order_status__in=[
                        Order.OrderStatus.IN_PROCESSING,
                        Order.OrderStatus.ACCEPTED,
                    ],
                )
                .values_list('name', flat=True)
                .distinct()
            )
            if active_store_names:
                store_names = ', '.join(active_store_names)
                return Response(
                    {
                        'detail': (
                            f'Невозможно удалить магазины с активными заказами. '
                            f'Сначала завершите или отмените все заказы в магазинах: {store_names}.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            deleted_count, _ = Store.objects.filter(
                uuid__in=candidate_uuids
            ).delete()

        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class StoreBySlugView(generics.RetrieveAPIView):
    queryset = Store.objects.select_related('region', 'admin_user').prefetch_related('photos', 'slides')
    serializer_class = StoreSerializer
    permission_classes = (AllowAny,)
    lookup_field = 'slug'


class StoreDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Store.objects.select_related('region', 'admin_user').prefetch_related('photos', 'slides')
    lookup_field = 'uuid'

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return StoreSerializer
        return StoreOwnerSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsStoreOwner()]


# ---------------------------------------------------------------------------
# Store Photos
# ---------------------------------------------------------------------------

class StorePhotoListCreateView(generics.ListCreateAPIView):
    queryset = StorePhoto.objects.select_related('store')
    filterset_class = StorePhotoFilter
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return StorePhotoCreateSerializer
        return StorePhotoSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


class StorePhotoGetMultipleView(generics.ListAPIView):
    queryset = StorePhoto.objects.select_related('store')
    serializer_class = StorePhotoSerializer
    permission_classes = (AllowAny,)
    filterset_class = StorePhotoFilter


class StorePhotoMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = StorePhoto.objects.filter(
            pk__in=ids, store__admin_user=request.user
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class StorePhotoDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StorePhoto.objects.select_related('store')
    serializer_class = StorePhotoCreateSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsStoreOwner()]


# ---------------------------------------------------------------------------
# BankTypes
# ---------------------------------------------------------------------------

class BankTypeListView(generics.ListAPIView):
    queryset = BankType.objects.all()
    serializer_class = BankTypeSerializer
    permission_classes = (AllowAny,)


class BankTypeDetailView(generics.RetrieveAPIView):
    queryset = BankType.objects.all()
    serializer_class = BankTypeSerializer
    permission_classes = (AllowAny,)


BankeTypeListView = BankTypeListView
BankeTypeDetailView = BankTypeDetailView


# ---------------------------------------------------------------------------
# StoreBankDetails
# ---------------------------------------------------------------------------

class StoreBankDetailListCreateView(generics.ListCreateAPIView):
    filterset_class = StoreBankDetailFilter
    search_fields = ('bank_account_number', 'bank_account_holder_name')
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return StoreBankDetail.objects.select_related('store', 'bank').filter(
            store__admin_user=self.request.user
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return StoreBankDetailSerializer
        return StoreBankDetailListSerializer


class StoreBankDetailDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated, IsStoreOwner)

    def get_queryset(self):
        return StoreBankDetail.objects.select_related('store', 'bank').filter(
            store__admin_user=self.request.user
        )

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return StoreBankDetailListSerializer
        return StoreBankDetailSerializer


# ---------------------------------------------------------------------------
# Balance Transactions
# ---------------------------------------------------------------------------

class StoreBalanceTransactionListView(generics.ListAPIView):
    serializer_class = StoreBalanceTransactionListSerializer
    permission_classes = (IsAuthenticated,)
    filterset_class = StoreBalanceTransactionFilter
    search_fields = ('description', 'store__name')

    def get_queryset(self):
        return (
            StoreBalanceTransaction.objects
            .select_related('store')
            .filter(store__admin_user=self.request.user)
            .order_by('-created_at')
        )


class StoreBalanceTransactionDetailView(generics.RetrieveAPIView):
    serializer_class = StoreBalanceTransactionSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return StoreBalanceTransaction.objects.select_related('store').filter(
            store__admin_user=self.request.user
        )


# ---------------------------------------------------------------------------
# Tariff Plans
# ---------------------------------------------------------------------------

class StoreTariffPlanListView(generics.ListAPIView):
    serializer_class = StoreTariffPlanSerializer
    permission_classes = (IsAuthenticated,)
    search_fields = ('store__name',)

    def get_queryset(self):
        return (
            StoreTariffPlan.objects
            .select_related('store')
            .filter(store__admin_user=self.request.user)
            .order_by('-created_at')
        )


class StoreTariffPlanDetailView(generics.RetrieveAPIView):
    serializer_class = StoreTariffPlanSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return StoreTariffPlan.objects.select_related('store').filter(
            store__admin_user=self.request.user
        )


# ---------------------------------------------------------------------------
# Balance actions
# ---------------------------------------------------------------------------

class ActivatePromocodeView(APIView):
    """
    POST /stores/balance/activate-promocode/

    FAT VIEW FIX: business logic (balance update + transaction creation +
    promocode marking) has been moved to stores.services.activate_promocode().
    The view now only handles HTTP concerns: auth, input validation, error
    mapping → HTTP status codes.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        idempotency_key = request.headers.get('Idempotency-Key')
        if idempotency_key:
            existing_tx = StoreBalanceTransaction.objects.filter(
                store__admin_user=request.user,
                idempotency_key=idempotency_key
            ).first()
            if existing_tx:
                return Response({'detail': 'Промокод успешно активирован.'}, status=status.HTTP_200_OK)

        serializer = ToActivatePromocodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code_value = serializer.validated_data['code']
        store_uuid = serializer.validated_data['store']

        try:
            with transaction.atomic():
                try:
                    store = Store.objects.select_for_update().get(
                        uuid=store_uuid, admin_user=request.user,
                    )
                except Store.DoesNotExist:
                    return Response(
                        {'detail': 'Магазин не найден или доступ запрещён.'},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                try:
                    activate_promocode(store, code_value, idempotency_key=idempotency_key)
                except PromocodeError as exc:
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {'detail': 'Операция отклонена. Нарушение целостности данных (например, недостаточный баланс).'},
                status=status.HTTP_409_CONFLICT,
            )

        logger.info(
            'promocode_activated store=%s code=%s user=%s',
            store.uuid, code_value, request.user.pk,
        )
        return Response({'detail': 'Промокод успешно активирован.'}, status=status.HTTP_200_OK)


class SetTariffPlanView(APIView):
    """
    POST /stores/balance/set/tariff-plans/

    FAT VIEW FIX: price matrix lookup + balance deduction + plan/transaction
    creation has been moved to stores.services.purchase_tariff().
    The view now only handles HTTP concerns.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        idempotency_key = request.headers.get('Idempotency-Key')
        if idempotency_key:
            existing_tx = StoreBalanceTransaction.objects.filter(
                store__admin_user=request.user,
                idempotency_key=idempotency_key
            ).first()
            if existing_tx:
                # If duplicating, we must still return the StoreTariffPlan data to match API contract.
                # However, since the front-end mostly cares about 200 OK or 201 Created and the same info,
                # we return the latest active tariff plan for this store.
                tariff_plan = StoreTariffPlan.objects.filter(store=existing_tx.store).order_by('-created_at').first()
                if tariff_plan:
                    return Response(StoreTariffPlanSerializer(tariff_plan).data, status=status.HTTP_200_OK)

        serializer = StoreTariffPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tariff = data['tariff']
        duration_type = data['duration_type']

        # Validate combination exists before touching the DB.
        if (tariff, duration_type) not in TARIFF_PRICES:
            return Response(
                {'detail': f'Недопустимая комбинация тарифа ({tariff}) и длительности ({duration_type}).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                try:
                    store = Store.objects.select_for_update().get(
                        uuid=data['store'], admin_user=request.user,
                    )
                except Store.DoesNotExist:
                    return Response(
                        {'detail': 'Магазин не найден или доступ запрещён.'},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                try:
                    tariff_plan = purchase_tariff(store, tariff, duration_type, idempotency_key=idempotency_key)
                except TariffError as exc:
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {'detail': 'Операция отклонена. Нарушение целостности данных (например, недостаточный баланс).'},
                status=status.HTTP_409_CONFLICT,
            )

        logger.info(
            'tariff_purchased store=%s tariff=%s duration=%s user=%s',
            store.uuid, tariff, duration_type, request.user.pk,
        )
        return Response(StoreTariffPlanSerializer(tariff_plan).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Slides — nested under Store
# ---------------------------------------------------------------------------

class StoreSlideListCreateView(generics.ListCreateAPIView):
    serializer_class = SlideSerializer
    search_fields = ('title',)
    ordering_fields = ('sort_order', 'created_at')

    def get_queryset(self):
        return Slide.objects.filter(store__uuid=self.kwargs['uuid']).select_related('store')

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        """
        R-2 FIX (TOCTOU — Slide Limit Race Condition):
        Previously: check_slide_limit() (unlocked count) + serializer.save()
        ran in two separate transactions, creating a TOCTOU window.

        Now: create_slide_locked() acquires a row-level lock on the Store,
        counts slides, and inserts — all in ONE atomic transaction. The view
        only handles the permission check (requires request.user) and sets
        serializer.instance so the response serializes the created object.
        """
        store = get_object_or_404(Store, uuid=self.kwargs['uuid'])
        if self.request.user != store.admin_user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Доступ разрешён только владельцу магазина.')
        # Lock store → count → INSERT happen atomically in the service.
        # serializer.instance is set so DRF can serialize the response.
        slide = create_slide_locked(store, serializer.validated_data)
        serializer.instance = slide


class StoreSlideDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SlideSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        return Slide.objects.filter(store__uuid=self.kwargs['uuid']).select_related('store')

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsStoreOwner()]


class StoreSlideMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, uuid):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = Slide.objects.filter(
            pk__in=ids, store__uuid=uuid, store__admin_user=request.user,
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class StoreSlideSetOrderingView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, uuid):
        store = get_object_or_404(Store, uuid=uuid, admin_user=request.user)
        items = request.data.get('slides', [])
        if not isinstance(items, list):
            return Response({'detail': 'Ожидается массив slides.'}, status=status.HTTP_400_BAD_REQUEST)

        if not items:
            return Response({'detail': 'Массив slides не может быть пустым.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(items) > MAX_BULK_OPERATIONS:
            return Response(
                {'detail': f'Нельзя обновить более {MAX_BULK_OPERATIONS} слайдов за один запрос.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invalid = [
            i for i, item in enumerate(items)
            if item.get('slide') is None or item.get('sort_order') is None
        ]
        if invalid:
            return Response(
                {
                    'detail': 'Каждый элемент должен содержать поля "slide" и "sort_order".',
                    'invalid_indices': invalid,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_map = {item['slide']: item['sort_order'] for item in items}

        # A-5 REFACTOR: atomic bulk-update delegated to stores.services.reorder_slides().
        # The service owns the transaction, the DB query, and the logger call.
        # This view only handles input validation and HTTP concerns.
        reorder_slides(store, order_map)

        return Response({'detail': 'Порядок слайдов обновлён.'}, status=status.HTTP_200_OK)
