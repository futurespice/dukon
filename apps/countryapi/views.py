from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.countryapi.models import Country, Region, City
from apps.countryapi.serializers import (
    ListCountrySerializer,
    ListRegionSerializer,
    ListCitySerializer,
)
from apps.countryapi.filters import RegionFilter, CityFilter


# ---------------------------------------------------------------------------
# Countries
# GET  /countryapi/countries/        — list (paginated, search)
# GET  /countryapi/countries/{id}/   — retrieve
# ---------------------------------------------------------------------------

class CountryListView(generics.ListAPIView):
    """
    GET /countryapi/countries/
    Supports: search, offset/limit pagination.
    """
    queryset = Country.objects.filter(is_active=True).order_by('name')
    serializer_class = ListCountrySerializer
    permission_classes = (AllowAny,)
    search_fields = ('name', 'code')


class CountryDetailView(generics.RetrieveAPIView):
    """GET /countryapi/countries/{id}/"""
    queryset = Country.objects.all()
    serializer_class = ListCountrySerializer
    permission_classes = (AllowAny,)


# ---------------------------------------------------------------------------
# Regions
# GET  /countryapi/regions/          — list (paginated, search, filter by country)
# GET  /countryapi/regions/{id}/     — retrieve
# ---------------------------------------------------------------------------

class RegionListView(generics.ListAPIView):
    """
    GET /countryapi/regions/
    Supports: search, offset/limit pagination, filter by country.
    """
    queryset = Region.objects.select_related('country').filter(is_active=True)
    serializer_class = ListRegionSerializer
    permission_classes = (AllowAny,)
    filterset_class = RegionFilter
    search_fields = ('name',)


class RegionDetailView(generics.RetrieveAPIView):
    """GET /countryapi/regions/{id}/"""
    queryset = Region.objects.select_related('country').all()
    serializer_class = ListRegionSerializer
    permission_classes = (AllowAny,)


# ---------------------------------------------------------------------------
# Cities
# GET  /countryapi/cities/           — list (paginated, search, filter by region)
# GET  /countryapi/cities/{id}/      — retrieve
# ---------------------------------------------------------------------------

class CityListView(generics.ListAPIView):
    """
    GET /countryapi/cities/
    Supports: search, offset/limit pagination, filter by region.
    """
    queryset = City.objects.select_related('region__country').filter(is_active=True)
    serializer_class = ListCitySerializer
    permission_classes = (AllowAny,)
    filterset_class = CityFilter
    search_fields = ('name',)


class CityDetailView(generics.RetrieveAPIView):
    """GET /countryapi/cities/{id}/"""
    queryset = City.objects.select_related('region__country').all()
    serializer_class = ListCitySerializer
    permission_classes = (AllowAny,)
