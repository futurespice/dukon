from django.db import transaction
from django.db.models import Exists, OuterRef, Count

from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.common.permissions import IsVerifiedUser
from apps.common.mixins import validate_bulk_ids
from apps.common.constants import MAX_BULK_OPERATIONS
from apps.products.models import (
    Photo, Category, Product, ProductModel, ProductPhoto, FavoriteProduct
)
from apps.products.serializers import (
    PhotoSerializer,
    CategorySerializer, CategoryListSerializer,
    CategoriesOrderingSerializer,
    ProductSerializer, ProductListSerializer, ProductCreateSerializer,
    ProductModelCreateSerializer, ProductModelListSerializer,
    ProductPhotoCreateSerializer, ProductPhotoListSerializer,
    FavoriteProductSerializer, FavoriteProductListSerializer,
    MyProductBulkItemSerializer,
    ChoiceStoreToImportSerializer,
    UploadFileToImportProductSerializer,
    ProductCreateCopySerializer,
)
from apps.products.filters import (
    CategoryFilter, ProductFilter,
    ProductModelFilter, ProductPhotoFilter,
)

# Fields updated by MyProductBulkUpdateView — kept as a constant to avoid
# duplication between the setattr loop and bulk_update(fields=...).
_BULK_UPDATE_FIELDS = (
    'name', 'short_description', 'description',
    'is_for_children', 'is_vegan', 'is_popular',
    'is_hidden', 'is_stop',
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product_qs_with_fav(request):
    """
    Base queryset with prefetch/select optimised for ProductListSerializer.

    Prefetch includes:
      - models__photos__image  — product variant photos
      - favorited_by           — used for _is_fav annotation fallback
      - store__photos          — StoreSerializer embeds photos
      - store__slides          — StoreSerializer embeds slides

    Without store__photos / store__slides Django would issue 2 extra SELECT
    queries per product row, turning a list of 20 products into 40+ extra queries.
    """
    qs = (
        Product.objects
        .select_related(
            'store__region',
            'store__admin_user',
            'category__parent__parent__parent',  # covers 3-level parent chain
        )
        .prefetch_related(
            'models__photos__image',
            'favorited_by',
            'store__photos',
            'store__slides',
        )
        .annotate(viewers_count=Count('viewers', distinct=True))
    )
    if request and request.user.is_authenticated:
        qs = qs.annotate(
            _is_fav=Exists(
                FavoriteProduct.objects.filter(
                    product=OuterRef('pk'),
                    user=request.user,
                )
            )
        )
    return qs


_CATEGORY_QS = Category.objects.select_related(
    'parent__parent__parent',
    'store',
)


def _product_visibility_filter(qs, user):
    """Apply is_hidden visibility rules consistently across list/detail views."""
    from django.db.models import Q as DQ
    if user and user.is_authenticated:
        if not user.is_staff:
            qs = qs.filter(DQ(is_hidden=False) | DQ(store__admin_user=user))
    else:
        qs = qs.filter(is_hidden=False)
    return qs


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

class PhotoListCreateView(generics.ListCreateAPIView):
    serializer_class = PhotoSerializer
    search_fields = ('name', 'alt_text')
    ordering_fields = ('name', 'created_at')
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        qs = Photo.objects.all()
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            user = self.request.user
            if user and user.is_authenticated:
                from django.db.models import Q as DQ
                qs = qs.filter(DQ(is_public=True) | DQ(uploaded_by=user))
            else:
                qs = qs.filter(is_public=True)
        return qs

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class PhotoDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PhotoSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        qs = Photo.objects.all()
        if self.request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if self.request.user.is_authenticated:
                qs = qs.filter(uploaded_by=self.request.user)
        return qs

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = _CATEGORY_QS
    filterset_class = CategoryFilter
    search_fields = ('name',)
    ordering_fields = ('order', 'name')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CategorySerializer
        return CategoryListSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsVerifiedUser()]


class CategoryGetMultipleView(generics.ListAPIView):
    queryset = _CATEGORY_QS
    serializer_class = CategoryListSerializer
    filterset_class = CategoryFilter
    search_fields = ('name',)
    ordering_fields = ('order', 'name')
    permission_classes = (AllowAny,)


class CategoryBulkCreateView(APIView):
    permission_classes = (IsVerifiedUser,)

    def post(self, request):
        if not isinstance(request.data, list):
            return Response(
                {'detail': 'Ожидается массив объектов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(request.data) > MAX_BULK_OPERATIONS:
            return Response(
                {'detail': f'Нельзя создать более {MAX_BULK_OPERATIONS} записей за один запрос.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = CategorySerializer(
            data=request.data, many=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CategoryMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = Category.objects.filter(
            pk__in=ids, store__admin_user=request.user
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class CategorySetOrderingView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = CategoriesOrderingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['categories']
        if len(items) > MAX_BULK_OPERATIONS:
            return Response(
                {'detail': f'Нельзя обновить более {MAX_BULK_OPERATIONS} категорий за один запрос.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order_map = {item['category']: item['order'] for item in items}
        cats = list(
            Category.objects.filter(
                pk__in=order_map.keys(),
                store__admin_user=request.user,
            )
        )
        for cat in cats:
            cat.order = order_map[cat.pk]
        if cats:
            Category.objects.bulk_update(cats, ['order'])
        return Response({'detail': 'Порядок обновлён.'}, status=status.HTTP_200_OK)


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    def get_queryset(self):
        qs = _CATEGORY_QS
        if self.request.method not in ('GET', 'HEAD', 'OPTIONS'):
            qs = qs.filter(store__admin_user=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return CategoryListSerializer
        return CategorySerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# ProductModels
# ---------------------------------------------------------------------------

class ProductModelListCreateView(generics.ListCreateAPIView):
    queryset = ProductModel.objects.select_related('product').prefetch_related('photos__image')
    filterset_class = ProductModelFilter
    search_fields = ('name',)
    ordering_fields = ('name', 'price', 'created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductModelCreateSerializer
        return ProductModelListSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsVerifiedUser()]


class ProductModelGetMultipleView(generics.ListAPIView):
    queryset = ProductModel.objects.select_related('product').prefetch_related('photos__image')
    serializer_class = ProductModelListSerializer
    filterset_class = ProductModelFilter
    search_fields = ('name',)
    ordering_fields = ('name', 'price', 'created_at')
    permission_classes = (AllowAny,)


class ProductModelMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = ProductModel.objects.filter(
            pk__in=ids, product__store__admin_user=request.user,
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class ProductModelDetailView(generics.RetrieveUpdateDestroyAPIView):
    def get_queryset(self):
        qs = ProductModel.objects.select_related('product').prefetch_related('photos__image')
        if self.request.method not in ('GET', 'HEAD', 'OPTIONS'):
            qs = qs.filter(product__store__admin_user=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ProductModelListSerializer
        return ProductModelCreateSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# ProductPhotos
# ---------------------------------------------------------------------------

class ProductPhotoListCreateView(generics.ListCreateAPIView):
    queryset = ProductPhoto.objects.select_related('product__product', 'image')
    filterset_class = ProductPhotoFilter
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductPhotoCreateSerializer
        return ProductPhotoListSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


class ProductPhotoGetMultipleView(generics.ListAPIView):
    queryset = ProductPhoto.objects.select_related('product__product', 'image')
    serializer_class = ProductPhotoListSerializer
    filterset_class = ProductPhotoFilter
    permission_classes = (AllowAny,)


class ProductPhotoMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = ProductPhoto.objects.filter(
            pk__in=ids, product__product__store__admin_user=request.user,
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class ProductPhotoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Restricts mutations to photos belonging to the requesting user's stores."""
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        qs = ProductPhoto.objects.select_related('product__product__store', 'image')
        if self.request.method not in ('GET', 'HEAD', 'OPTIONS'):
            qs = qs.filter(product__product__store__admin_user=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ProductPhotoListSerializer
        return ProductPhotoCreateSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class ProductListCreateView(generics.ListCreateAPIView):
    filterset_class = ProductFilter
    search_fields = ('name', 'short_description', 'article')
    ordering_fields = ('name', 'created_at')

    def get_queryset(self):
        return _product_visibility_filter(
            _product_qs_with_fav(self.request),
            self.request.user if self.request else None,
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsVerifiedUser()]


class ProductGetMultipleView(generics.ListAPIView):
    serializer_class = ProductListSerializer
    filterset_class = ProductFilter
    search_fields = ('name', 'short_description', 'article')
    ordering_fields = ('name', 'created_at')
    permission_classes = (AllowAny,)

    def get_queryset(self):
        return _product_visibility_filter(
            _product_qs_with_fav(self.request),
            self.request.user if self.request else None,
        )


class ProductMultipleDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ids, err = validate_bulk_ids(request.data)
        if err:
            return err
        deleted_count, _ = Product.objects.filter(
            pk__in=ids, store__admin_user=request.user
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    def get_queryset(self):
        qs = _product_qs_with_fav(self.request)
        user = self.request.user if self.request else None
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _product_visibility_filter(qs, user)
        return qs.filter(store__admin_user=user)

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ProductListSerializer
        return ProductSerializer

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]


class ProductBulkCreateView(APIView):
    permission_classes = (IsVerifiedUser,)

    def post(self, request):
        data = request.data if isinstance(request.data, list) else [request.data]
        if len(data) > MAX_BULK_OPERATIONS:
            return Response(
                {'detail': f'Нельзя создать более {MAX_BULK_OPERATIONS} продуктов за один запрос.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ProductSerializer(data=data, many=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductCreateCopyView(APIView):
    permission_classes = (IsVerifiedUser,)

    def post(self, request):
        serializer = ProductCreateCopySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data['product_id']

        try:
            original = (
                Product.objects
                .prefetch_related('models__photos')
                .get(pk=product_id, store__admin_user=request.user)
            )
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Продукт не найден или доступ запрещён.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            _name_max = Product._meta.get_field('name').max_length
            _suffix = ' (копия)'
            _base = original.name[:_name_max - len(_suffix)]
            copy = Product.objects.create(
                store=original.store,
                category=original.category,
                name=f'{_base}{_suffix}',
                short_description=original.short_description,
                description=original.description,
                is_for_children=original.is_for_children,
                is_vegan=original.is_vegan,
                is_popular=original.is_popular,
                is_hidden=True,
                is_stop=original.is_stop,
            )
            for model in original.models.all():
                new_model = ProductModel.objects.create(
                    product=copy,
                    name=model.name,
                    quantity=model.quantity,
                    price=model.price,
                )
                for photo in model.photos.all():
                    ProductPhoto.objects.create(product=new_model, image=photo.image)

        return Response(ProductCreateSerializer(copy).data, status=status.HTTP_201_CREATED)


class ProductExportView(APIView):
    """Not yet implemented. Restricted to admin users."""
    from rest_framework.permissions import IsAdminUser
    permission_classes = (IsAdminUser,)

    def post(self, request):
        serializer = ChoiceStoreToImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {'detail': 'Функция экспорта продуктов пока не реализована.'},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class ProductImportView(APIView):
    """Not yet implemented. Restricted to admin users."""
    from rest_framework.permissions import IsAdminUser
    permission_classes = (IsAdminUser,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = UploadFileToImportProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {'detail': 'Функция импорта продуктов пока не реализована.'},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

class FavoriteListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsVerifiedUser,)

    def get_queryset(self):
        return FavoriteProduct.objects.filter(user=self.request.user).select_related(
            'product__store', 'product__category'
        ).prefetch_related('product__models__photos__image')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return FavoriteProductSerializer
        return FavoriteProductListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FavoriteDeleteView(generics.DestroyAPIView):
    permission_classes = (IsVerifiedUser,)
    serializer_class = FavoriteProductSerializer

    def get_queryset(self):
        return FavoriteProduct.objects.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# my-products (bulk create / bulk update)
# ---------------------------------------------------------------------------

class MyProductBulkCreateView(APIView):
    permission_classes = (IsVerifiedUser,)

    def post(self, request):
        if not isinstance(request.data, list):
            return Response(
                {'detail': 'Ожидается массив объектов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(request.data) > MAX_BULK_OPERATIONS:
            return Response(
                {'detail': f'Нельзя создать более {MAX_BULK_OPERATIONS} продуктов за один запрос.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = MyProductBulkItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data

        from apps.stores.models import Store
        from apps.products.models import Category as Cat

        # M-5 FIX: batch-fetch all required stores in ONE query instead of
        # one SELECT per unique store UUID (up to MAX_BULK_OPERATIONS hits).
        # Old code: per-item Store.objects.get() inside a loop → N SELECTs.
        # New code: one Store.objects.filter(uuid__in=...) → 1 SELECT.
        store_uuids = {item['store'] for item in items}
        store_cache = {
            s.uuid: s
            for s in Store.objects.filter(uuid__in=store_uuids, admin_user=request.user)
        }

        errors = [
            {'store': str(uuid), 'reason': 'Магазин не найден или доступ запрещён.'}
            for uuid in store_uuids
            if uuid not in store_cache
        ]

        if errors:
            return Response(
                {
                    'detail': 'Один или несколько магазинов не найдены. Ни один продукт не создан.',
                    'errors': errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        category_uuids = {item['category'] for item in items if item.get('category')}
        category_map = (
            {str(c.uuid): c for c in Cat.objects.filter(uuid__in=category_uuids)}
            if category_uuids else {}
        )

        with transaction.atomic():
            product_objs = [
                Product(
                    store=store_cache[item['store']],
                    category=category_map.get(str(item['category'])) if item.get('category') else None,
                    name=item['name'],
                    short_description=item.get('short_description', ''),
                    description=item.get('description', ''),
                    is_for_children=item.get('is_for_children', False),
                    is_vegan=item.get('is_vegan', False),
                    is_popular=item.get('is_popular', False),
                    is_hidden=item.get('is_hidden', False),
                    is_stop=item.get('is_stop', False),
                )
                for item in items
            ]
            created = Product.objects.bulk_create(product_objs)

            ProductModel.objects.bulk_create([
                ProductModel(
                    product=product,
                    name=product.name,
                    quantity=0,
                    price=items[i].get('price', 0),
                )
                for i, product in enumerate(created)
            ])

        return Response(ProductCreateSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class MyProductBulkUpdateView(APIView):
    """
    PATCH /products/my/bulk-update/

    FIX #2 (CRITICAL — N+1 inside transaction):
    The previous implementation issued one SELECT per item inside a
    transaction.atomic() block:

        for item in items:                            # up to 100 iterations
            product = Product.objects.filter(         # 1 SELECT each = 100 queries
                uuid=item['uuid'], store__admin_user=request.user
            ).first()

    At MAX_BULK_OPERATIONS=100 this is 100 SELECTs holding an open DB
    connection. Under load this exhausts the connection pool.

    Fix: pre-fetch all products in a single query, build a uuid→instance map,
    then iterate over the map in Python — zero extra DB round trips inside the loop.
    """
    permission_classes = (IsAuthenticated,)

    def patch(self, request):
        if not isinstance(request.data, list):
            return Response(
                {'detail': 'Ожидается массив объектов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(request.data) > MAX_BULK_OPERATIONS:
            return Response(
                {'detail': f'Нельзя обновить более {MAX_BULK_OPERATIONS} продуктов за один запрос.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MyProductBulkItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data

        # Collect UUIDs that were actually provided (items without uuid are skipped).
        uuids = [item['uuid'] for item in items if item.get('uuid')]

        # FIX #2: One batch SELECT for all products — replaces N per-item queries.
        products_map = {
            str(p.uuid): p
            for p in Product.objects.filter(
                uuid__in=uuids,
                store__admin_user=request.user,
            )
        }

        updated = []
        not_found = []

        for item in items:
            if not item.get('uuid'):
                continue
            product = products_map.get(str(item['uuid']))
            if not product:
                not_found.append(str(item['uuid']))
                continue
            for field in _BULK_UPDATE_FIELDS:
                if field in item:
                    setattr(product, field, item[field])
            updated.append(product)

        if updated:
            with transaction.atomic():
                Product.objects.bulk_update(updated, fields=list(_BULK_UPDATE_FIELDS))

        response_data = ProductCreateSerializer(updated, many=True).data
        if not_found:
            return Response(
                {'products': response_data, 'not_found': not_found},
                status=status.HTTP_200_OK,
            )
        return Response(response_data, status=status.HTTP_200_OK)
