import logging

from apps.stores.serializers import StoreSerializer

from rest_framework import serializers

from apps.products.models import (
    Photo, Category, Product, ProductModel, ProductPhoto, FavoriteProduct
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Photo
# ---------------------------------------------------------------------------

class PhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Photo
        fields = (
            'id', 'thumbnail_image', 'medium_image', 'image',
            'created_at', 'updated_at',
            'name', 'alt_text', 'description', 'is_public',
            'uploaded_by',
        )
        read_only_fields = (
            'id', 'created_at', 'updated_at',
            'thumbnail_image', 'medium_image',
            'uploaded_by',
        )


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

def _has_ancestor_cycle(candidate, target_pk: int) -> bool:
    """
    Walk up the parent chain starting from `candidate` and check whether
    `target_pk` appears anywhere in that chain (which would mean making
    `candidate` a parent of `target_pk` creates a cycle).

    AUDIT N+1 FIX: uses `parent_id` (the raw FK integer) to avoid triggering
    an extra SELECT on every iteration. `parent_id` is always available on the
    already-loaded instance without hitting the database, because Django stores
    FK ids as plain attributes alongside the related-object descriptor.

    When we do need to fetch the next ancestor (parent not already in memory),
    we load it with `select_related('parent__parent__parent')` so a single
    query covers up to 4 levels at once, amortising the cost for deep trees.
    """
    visited: set[int] = set()
    current = candidate

    while current is not None:
        pk = current.pk
        if pk in visited:
            # Pre-existing cycle in the DB — treat as a cycle to be safe.
            return True
        visited.add(pk)
        if pk == target_pk:
            return True

        parent_id = current.parent_id  # raw FK — no DB hit
        if parent_id is None:
            break

        # If the parent object is already loaded (e.g. via select_related),
        # reuse it. Otherwise, fetch with a 3-level select_related to reduce
        # round-trips for deeper trees.
        if current.parent_id is not None and hasattr(current, '_state'):
            # Check if parent is already in the deferred-fields cache
            parent_loaded = (
                hasattr(current, '__dict__')
                and 'parent' in current.__dict__
                and current.__dict__['parent'] is not None
            )
            if parent_loaded:
                current = current.__dict__['parent']
                continue

        # Fetch the next ancestor with 3 additional levels pre-loaded.
        try:
            current = (
                Category.objects
                .select_related('parent__parent__parent')
                .get(pk=parent_id)
            )
        except Category.DoesNotExist:
            break

    return False


# A-2: Maximum nesting depth for the category parent chain in API responses.
# Categories at depth > _MAX_PARENT_DEPTH are truncated to None.
# Prevents stack-overflow on pathological hierarchies and caps response size.
_MAX_PARENT_DEPTH = 5


class ParentCategorySerializer(serializers.ModelSerializer):
    """
    A-2 REFACTOR: added depth guard to prevent unbounded recursion.

    Previously `get_parent` called ParentCategorySerializer(obj.parent).data
    with no context, losing track of nesting level. A 100-level hierarchy
    would recurse 100 times; a pre-existing DB cycle would loop forever.

    Fix: pass `_depth` through serializer context and stop at _MAX_PARENT_DEPTH.
    """
    parent = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'name', 'parent')

    def get_parent(self, obj):
        if obj.parent is None:
            return None
        depth = self.context.get('_depth', 0)
        if depth >= _MAX_PARENT_DEPTH:
            # Silently truncate instead of raising — the client gets a valid
            # partial tree rather than an error for deep hierarchies.
            return None
        return ParentCategorySerializer(
            obj.parent,
            context={**self.context, '_depth': depth + 1},
        ).data


class CategoryListSerializer(serializers.ModelSerializer):
    parent = ParentCategorySerializer(read_only=True)

    class Meta:
        model = Category
        fields = (
            'id', 'parent', 'name', 'order',
            'is_hidden', 'image', 'icon',
        )
        read_only_fields = ('id', 'image', 'icon')


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            'id', 'uuid', 'name', 'order',
            'is_hidden', 'image', 'icon',
            'store', 'parent',
        )
        read_only_fields = ('id', 'image', 'icon')

    # ROUND-2 CRITICAL #3: Prevent creating categories in stores the user doesn't own.
    def validate_store(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.admin_user != request.user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Доступ запрещён: вы не владелец этого магазина.')
        return value

    def validate_parent(self, value):
        """
        Prevent circular parent references at any depth.

        SMALL FIX #25: the previous check only caught direct self-reference
        (A.parent = A). A 2-level cycle (A → B → A) would pass validation and
        corrupt the tree. Now we walk the full ancestor chain of `value` to
        confirm that the current instance doesn't appear anywhere in it.

        AUDIT N+1 FIX: _has_ancestor_cycle now uses parent_id (raw FK) and
        batched select_related to avoid per-level lazy loads.
        """
        if value is None:
            return value

        if not self.instance:
            # Creating a new category — no cycle possible yet.
            return value

        if value.pk == self.instance.pk:
            raise serializers.ValidationError(
                'Категория не может быть родителем самой себя.'
            )

        if _has_ancestor_cycle(value, self.instance.pk):
            raise serializers.ValidationError(
                'Назначение этого родителя создаст циклическую зависимость в дереве категорий.'
            )

        return value

    def validate(self, attrs):
        parent = attrs.get('parent')
        store = attrs.get('store') or (self.instance.store if self.instance else None)
        if parent and store and parent.store_id != store.pk:
            raise serializers.ValidationError({
                'parent': 'Родительская категория должна принадлежать тому же магазину.'
            })
        return attrs


class CategoryOrderingItemSerializer(serializers.Serializer):
    category = serializers.IntegerField()
    order = serializers.IntegerField()


class CategoriesOrderingSerializer(serializers.Serializer):
    categories = CategoryOrderingItemSerializer(many=True)


# ---------------------------------------------------------------------------
# ProductPhoto (nested)
# ---------------------------------------------------------------------------

class ProductPhotoNestedSerializer(serializers.ModelSerializer):
    image = PhotoSerializer(read_only=True)

    class Meta:
        model = ProductPhoto
        fields = ('id', 'image')


class ProductPhotoShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPhoto
        fields = ('id', 'image')


# ---------------------------------------------------------------------------
# ProductModel
# ---------------------------------------------------------------------------

class ProductModelListSerializer(serializers.ModelSerializer):
    photos = ProductPhotoNestedSerializer(many=True, read_only=True)

    class Meta:
        model = ProductModel
        fields = ('id', 'photos', 'name', 'quantity', 'price')
        read_only_fields = ('id',)


class ProductModelCreateSerializer(serializers.ModelSerializer):
    photos = ProductPhotoShortSerializer(many=True, read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    class Meta:
        model = ProductModel
        fields = ('id', 'photos', 'name', 'quantity', 'price', 'product')
        read_only_fields = ('id',)

    # ROUND-2 CRITICAL #1: Prevent creating ProductModels for products in other users' stores.
    def validate_product(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.store.admin_user != request.user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Доступ запрещён: вы не владелец магазина этого продукта.')
        return value


# ---------------------------------------------------------------------------
# ProductPhoto (top-level CRUD)
# ---------------------------------------------------------------------------

class ProductPhotoListSerializer(serializers.ModelSerializer):
    image = PhotoSerializer(read_only=True)

    class Meta:
        model = ProductPhoto
        fields = ('id', 'image')


class ProductPhotoCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPhoto
        fields = ('id', 'product', 'image')
        read_only_fields = ('id',)

    # ROUND-2 CRITICAL #2: Prevent attaching photos to ProductModels in other users' stores.
    def validate_product(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.product.store.admin_user != request.user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Доступ запрещён: вы не владелец магазина этого продукта.')
        return value


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class ProductListSerializer(serializers.ModelSerializer):
    """Full nested read serializer. Uses _is_fav annotation to avoid N+1 queries."""
    category = CategorySerializer(read_only=True)
    store = StoreSerializer(read_only=True)
    models = ProductModelListSerializer(many=True, read_only=True)
    is_favorite = serializers.SerializerMethodField()
    viewers_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'category', 'store', 'models',
            'is_favorite', 'viewers_count',
            'created_at', 'updated_at',
            'article', 'uuid', 'name', 'short_description', 'description',
            'is_for_children', 'is_vegan', 'is_popular', 'is_hidden', 'is_stop',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'is_favorite', 'viewers_count')

    def get_is_favorite(self, obj):
        # Fast path: annotation provided by _product_qs_with_fav()
        if hasattr(obj, '_is_fav'):
            return obj._is_fav
        # Slow path: fallback for objects fetched outside _product_qs_with_fav.
        # Log a warning so developers notice the N+1 query in logs/Sentry.
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            logger.warning(
                'ProductListSerializer: _is_fav annotation missing on product pk=%s. '
                'Falling back to per-object query (N+1). '
                'Always use _product_qs_with_fav() when serializing product lists.',
                obj.pk,
            )
            return obj.favorited_by.filter(user=request.user).exists()
        return False

    def get_viewers_count(self, obj):
        # Fast path: provided by annotate(viewers_count=Count('viewers', distinct=True)).
        val = getattr(obj, 'viewers_count', None)
        if val is not None:
            return val
        # M-4 FIX: fallback for objects fetched outside _product_qs_with_fav()
        # (e.g. ProductDetailView, FavoriteListCreateView).
        # Without this guard, missing annotation raises AttributeError → 500.
        logger.warning(
            'ProductListSerializer: viewers_count annotation missing on product pk=%s. '
            'Falling back to per-object query (N+1). '
            'Always use _product_qs_with_fav() when serializing product lists.',
            obj.pk,
        )
        return obj.viewers.count()


class ProductSerializer(serializers.ModelSerializer):
    """Write serializer for create/update."""
    models = ProductModelListSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            'id', 'models', 'created_at', 'updated_at',
            'article', 'uuid', 'name', 'short_description', 'description',
            'is_for_children', 'is_vegan', 'is_popular', 'is_hidden', 'is_stop',
            'store', 'category', 'viewers',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'viewers')

    def validate_store(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.admin_user != request.user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Доступ запрещён: вы не владелец этого магазина.')
        return value

    def validate(self, attrs):
        category = attrs.get('category')
        store = attrs.get('store') or (self.instance.store if self.instance else None)
        if category and store and category.store_id != store.pk:
            raise serializers.ValidationError({
                'category': 'Категория должна принадлежать тому же магазину.'
            })
        return attrs


class ProductCreateSerializer(ProductSerializer):
    """
    A-1 REFACTOR: was a 100% duplicate of ProductSerializer — identical
    Meta, fields, read_only_fields, validate_store, and validate.
    Now inherits everything from ProductSerializer.

    Kept as a separate named class so all view imports stay unchanged
    (ProductCreateSerializer is referenced in products/views.py and
    used as the response serializer for bulk-create and copy endpoints).
    """
    pass


# ---------------------------------------------------------------------------
# FavoriteProduct
# ---------------------------------------------------------------------------

class FavoriteProductListSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = FavoriteProduct
        fields = ('id', 'product')
        read_only_fields = ('id',)


class FavoriteProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = FavoriteProduct
        fields = ('id', 'product')
        read_only_fields = ('id',)

    def validate_product(self, value):
        request = self.context.get('request')
        if request and FavoriteProduct.objects.filter(user=request.user, product=value).exists():
            raise serializers.ValidationError('Этот продукт уже в избранном.')
        return value

    def create(self, validated_data):
        # TOCTOU FIX: validate_product() uses .exists() which has a race window.
        # Two concurrent POST requests both pass the check, then both call
        # super().create() — the second hits unique_together → IntegrityError → 500.
        # Fix: catch IntegrityError and convert to a controlled 400.
        from django.db import IntegrityError
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError(
                {'продукт': 'Этот продукт уже в избранном.'}
            )


# ---------------------------------------------------------------------------
# Bulk create/update
# ---------------------------------------------------------------------------

class MyProductBulkItemSerializer(serializers.Serializer):
    store = serializers.UUIDField()
    uuid = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=255)
    category = serializers.UUIDField(required=False, allow_null=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)
    mass_of_product = serializers.CharField(required=False, allow_blank=True)
    calories = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    image = serializers.URLField(required=False, allow_blank=True)
    short_description = serializers.CharField(required=False, allow_blank=True, default='')
    is_for_children = serializers.BooleanField(required=False, default=False)
    is_vegan = serializers.BooleanField(required=False, default=False)
    is_popular = serializers.BooleanField(required=False, default=False)
    is_hidden = serializers.BooleanField(required=False, default=False)
    is_stop = serializers.BooleanField(required=False, default=False)


class ChoiceStoreToImportSerializer(serializers.Serializer):
    store = serializers.UUIDField()


class UploadFileToImportProductSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    store = serializers.UUIDField()


class ProductCreateCopySerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
