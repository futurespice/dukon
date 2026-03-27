from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'is_read', 'created_at', 'updated_at', 'title', 'description')
        read_only_fields = ('id', 'created_at', 'updated_at', 'is_read')
        # is_read is a BooleanField — returned as proper bool (True/False), not string
