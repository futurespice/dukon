from django.urls import path
from apps.orders import views

urlpatterns = [
    # Store-owner view (orders from their stores)
    path('', views.OrderListCreateView.as_view(), name='order-list'),
    path('get-multiple/', views.OrderGetMultipleView.as_view(), name='order-get-multiple'),
    path('multiple-delete/', views.OrderMultipleDeleteView.as_view(), name='order-multiple-delete'),

    # Client endpoints
    path('my/', views.OrderMyListView.as_view(), name='order-my-list'),
    # Backward-compatible alias
    path('history/list/', views.OrderHistoryListView.as_view(), name='order-history-list'),

    # Public guest tracking: GET /orders/track/?order_id=42&phone=+996555...
    path('track/', views.OrderTrackView.as_view(), name='order-track'),

    path('<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('<int:pk>/upload-check/', views.OrderUploadCheckView.as_view(), name='order-upload-check'),
]
