from django_filters import rest_framework as filters
from apps.products.models import Category, Product, ProductModel, ProductPhoto


class CategoryFilter(filters.FilterSet):
    store = filters.UUIDFilter(field_name='store__uuid')
    store__slug = filters.CharFilter(field_name='store__slug')
    is_hidden = filters.BooleanFilter(field_name='is_hidden')
    parent = filters.NumberFilter(field_name='parent__id')

    class Meta:
        model = Category
        fields = ['store', 'store__slug', 'is_hidden', 'parent']


class ProductFilter(filters.FilterSet):
    category = filters.NumberFilter(field_name='category__id')
    category__is_hidden = filters.BooleanFilter(field_name='category__is_hidden')
    store = filters.UUIDFilter(field_name='store__uuid')
    store__slug = filters.CharFilter(field_name='store__slug')
    is_popular = filters.BooleanFilter(field_name='is_popular')
    is_for_children = filters.BooleanFilter(field_name='is_for_children')
    is_vegan = filters.BooleanFilter(field_name='is_vegan')
    is_hidden = filters.BooleanFilter(field_name='is_hidden')
    is_stop = filters.BooleanFilter(field_name='is_stop')
    article = filters.CharFilter(field_name='article', lookup_expr='icontains')
    store__region = filters.NumberFilter(field_name='store__region__id')
    store__region__region = filters.NumberFilter(field_name='store__region__region__id')
    store__region__region__country = filters.NumberFilter(
        field_name='store__region__region__country__id'
    )
    price = filters.NumberFilter(method='filter_by_price')

    def filter_by_price(self, queryset, name, value):
        return queryset.filter(models__price__lte=value).distinct()

    class Meta:
        model = Product
        fields = [
            'category', 'store', 'is_popular', 'is_for_children',
            'is_vegan', 'is_hidden', 'is_stop', 'article',
        ]


class ProductModelFilter(filters.FilterSet):
    product = filters.NumberFilter(field_name='product__id')
    product__store = filters.UUIDFilter(field_name='product__store__uuid')
    product__store__slug = filters.CharFilter(field_name='product__store__slug')

    class Meta:
        model = ProductModel
        fields = ['product', 'product__store', 'product__store__slug']


class ProductPhotoFilter(filters.FilterSet):
    product__product__store = filters.UUIDFilter(
        field_name='product__product__store__uuid'
    )
    product__product__store__slug = filters.CharFilter(
        field_name='product__product__store__slug'
    )

    class Meta:
        model = ProductPhoto
        fields = ['product__product__store', 'product__product__store__slug']
