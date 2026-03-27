from django.urls import path
from apps.notifications import views

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('mark_all_as_read/', views.NotificationMarkAllAsReadView.as_view(), name='notification-mark-all-read'),
    path('bulk-mark-read/', views.NotificationBulkMarkAsReadView.as_view(), name='notification-bulk-mark-read'),
    path('unread-count/', views.NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('<int:pk>/', views.NotificationDetailView.as_view(), name='notification-detail'),
    path('<int:pk>/mark_as_read/', views.NotificationMarkAsReadView.as_view(), name='notification-mark-read'),
]
