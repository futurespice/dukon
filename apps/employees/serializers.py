from django.contrib.auth.hashers import make_password

from rest_framework import serializers

from apps.employees.models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    """
    Used for create/update/retrieve and list views.
    'token' is excluded here — it is a session credential and must only be
    returned in the login response. Exposing it in list endpoints would allow
    any store owner to impersonate their employees' sessions trivially.
    """
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Employee
        fields = (
            'id', 'created_at', 'updated_at',
            'username', 'password', 'first_name', 'last_name',
            'position', 'is_active', 'store',
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'is_active')
        extra_kwargs = {'password': {'write_only': True, 'required': False}}

    # AUDIT-3 FIX #2 (CRITICAL): Prevent IDOR — creating employees in stores
    # the requesting user doesn't own.
    def validate_store(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.admin_user != request.user:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Доступ запрещён: вы не владелец этого магазина.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        employee = Employee(**validated_data)
        if password:
            employee.password = make_password(password)
        employee.save()
        return employee

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.password = make_password(password)
        instance.save()
        return instance


class EmployeeLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=255)
    password = serializers.CharField(max_length=128)
