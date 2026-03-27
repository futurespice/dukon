from django_filters import rest_framework as filters
from apps.countryapi.models import Region, City


class RegionFilter(filters.FilterSet):
    country = filters.NumberFilter(field_name='country__id')

    class Meta:
        model = Region
        fields = ['country']


class CityFilter(filters.FilterSet):
    region = filters.NumberFilter(field_name='region__id')

    class Meta:
        model = City
        fields = ['region']
