from rest_framework import serializers
from apps.countryapi.models import Country, Region, City


class ListCountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'code', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class ListRegionSerializer(serializers.ModelSerializer):
    country = ListCountrySerializer(read_only=True)
    country_id = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        source='country',
        write_only=True,
    )

    class Meta:
        model = Region
        fields = ('id', 'name', 'country', 'country_id', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class ListCitySerializer(serializers.ModelSerializer):
    region = ListRegionSerializer(read_only=True)
    region_id = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(),
        source='region',
        write_only=True,
    )

    class Meta:
        model = City
        fields = ('id', 'name', 'region', 'region_id', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')
