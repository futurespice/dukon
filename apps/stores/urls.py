from django.urls import path

from apps.stores import views

urlpatterns = [
    # ---- Stores ----
    path('', views.StoreListCreateView.as_view(), name='store-list'),
    path('get-multiple/', views.StoreGetMultipleView.as_view(), name='store-get-multiple'),
    path('multiple-delete/', views.StoreMultipleDeleteView.as_view(), name='store-multiple-delete'),
    path('by-slug/<slug:slug>/', views.StoreBySlugView.as_view(), name='store-by-slug'),
    path('<uuid:uuid>/', views.StoreDetailView.as_view(), name='store-detail'),

    # ---- Bank details ----
    path('bank-details/', views.StoreBankDetailListCreateView.as_view(), name='store-bank-detail-list'),
    path('bank-details/<int:pk>/', views.StoreBankDetailDetailView.as_view(), name='store-bank-detail-detail'),

    # ---- Store Photos ----
    path('photos/', views.StorePhotoListCreateView.as_view(), name='store-photo-list'),
    path('photos/get-multiple/', views.StorePhotoGetMultipleView.as_view(), name='store-photo-get-multiple'),
    path('photos/multiple-delete/', views.StorePhotoMultipleDeleteView.as_view(), name='store-photo-multiple-delete'),
    path('photos/<int:pk>/', views.StorePhotoDetailView.as_view(), name='store-photo-detail'),

    # ---- BankTypes ----
    path('banke-types/', views.BankTypeListView.as_view(), name='banke-type-list'),
    path('banke-types/<int:pk>/', views.BankTypeDetailView.as_view(), name='banke-type-detail'),

    # ---- Balance Transactions ----
    path('balance-transactions/', views.StoreBalanceTransactionListView.as_view(), name='store-balance-transaction-list'),
    path('balance-transactions/<int:pk>/', views.StoreBalanceTransactionDetailView.as_view(), name='store-balance-transaction-detail'),

    # ---- Tariff Plan Transactions ----
    path('tariff-plans-transactions/', views.StoreTariffPlanListView.as_view(), name='store-tariff-plan-list'),
    path('tariff-plans-transactions/<int:pk>/', views.StoreTariffPlanDetailView.as_view(), name='store-tariff-plan-detail'),

    # ---- Balance actions ----
    path('balance/set/promocode/', views.ActivatePromocodeView.as_view(), name='balance-set-promocode'),
    path('balance/set/tariff-plans/', views.SetTariffPlanView.as_view(), name='balance-set-tariff-plan'),

    # ---- Slides nested under Store  /stores/{uuid}/slides/ ----
    path('<uuid:uuid>/slides/', views.StoreSlideListCreateView.as_view(), name='store-slide-list'),
    path('<uuid:uuid>/slides/multiple-delete/', views.StoreSlideMultipleDeleteView.as_view(), name='store-slide-multiple-delete'),
    path('<uuid:uuid>/slides/set-ordering/', views.StoreSlideSetOrderingView.as_view(), name='store-slide-set-ordering'),
    path('<uuid:uuid>/slides/<int:pk>/', views.StoreSlideDetailView.as_view(), name='store-slide-detail'),
]
