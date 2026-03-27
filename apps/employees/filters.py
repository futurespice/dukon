from django_filters import rest_framework as filters
from apps.employees.models import Employee


class EmployeeFilter(filters.FilterSet):
    store = filters.UUIDFilter(field_name='store__uuid')
    store__slug = filters.CharFilter(field_name='store__slug')
    position = filters.ChoiceFilter(choices=Employee.Position.choices)
    is_active = filters.BooleanFilter(field_name='is_active')

    class Meta:
        model = Employee
        fields = ['store', 'store__slug', 'position', 'is_active']
