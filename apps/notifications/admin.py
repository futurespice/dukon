from django.contrib import admin
from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('title', 'description', 'user__phone')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')
    # AUDIT N+1 FIX: 'user' appears in list_display — each row previously
    # triggered a separate SELECT for the user object.
    list_select_related = ('user',)
