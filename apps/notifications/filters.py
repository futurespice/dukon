from django_filters import rest_framework as filters
from apps.notifications.models import Notification


class NotificationFilter(filters.FilterSet):
    is_read = filters.BooleanFilter(field_name='is_read')

    class Meta:
        model = Notification
        fields = ['is_read']
