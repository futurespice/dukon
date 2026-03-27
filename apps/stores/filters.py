from django_filters import rest_framework as filters

from apps.stores.models import Store, StorePhoto, StoreBankDetail, StoreBalanceTransaction, Slide


class StoreFilter(filters.FilterSet):
    region = filters.NumberFilter(field_name='region__id')
    region__region = filters.NumberFilter(field_name='region__region__id')
    region__region__country = filters.NumberFilter(field_name='region__region__country__id')
    tariff_plan = filters.CharFilter(field_name='tariff_plan')
    # AUDIT #4: admin_user removed — exposing it on a public endpoint enabled
    # user enumeration (GET /stores/?admin_user=1 reveals all user stores).

    class Meta:
        model = Store
        fields = ['region', 'tariff_plan']


class StorePhotoFilter(filters.FilterSet):
    store = filters.UUIDFilter(field_name='store__uuid')

    class Meta:
        model = StorePhoto
        fields = ['store']


class StoreBankDetailFilter(filters.FilterSet):
    store = filters.UUIDFilter(field_name='store__uuid')
    bank = filters.NumberFilter(field_name='bank__id')

    class Meta:
        model = StoreBankDetail
        fields = ['store', 'bank']


class StoreBalanceTransactionFilter(filters.FilterSet):
    store = filters.UUIDFilter(field_name='store__uuid')
    transaction_type = filters.CharFilter(field_name='transaction_type')
    status = filters.CharFilter(field_name='status')

    class Meta:
        model = StoreBalanceTransaction
        fields = ['store', 'transaction_type', 'status']


class SlideFilter(filters.FilterSet):
    store = filters.UUIDFilter(field_name='store__uuid')
    store__slug = filters.CharFilter(field_name='store__slug')

    class Meta:
        model = Slide
        fields = ['store', 'store__slug']
