from django.urls import path
from apps.products import views

urlpatterns = [
    # ---- Products ----
    path('', views.ProductListCreateView.as_view(), name='product-list'),
    path('get-multiple/', views.ProductGetMultipleView.as_view(), name='product-get-multiple'),
    path('multiple-delete/', views.ProductMultipleDeleteView.as_view(), name='product-multiple-delete'),
    path('bulk-create/', views.ProductBulkCreateView.as_view(), name='product-bulk-create'),
    path('create-copy/', views.ProductCreateCopyView.as_view(), name='product-create-copy'),
    path('export/', views.ProductExportView.as_view(), name='product-export'),
    path('import/', views.ProductImportView.as_view(), name='product-import'),
    path('<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),

    # ---- Photos (universal gallery) ----
    path('photos/', views.PhotoListCreateView.as_view(), name='photo-list'),
    path('photos/<int:pk>/', views.PhotoDetailView.as_view(), name='photo-detail'),

    # ---- Categories ----
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list'),
    path('categories/get-multiple/', views.CategoryGetMultipleView.as_view(), name='category-get-multiple'),
    path('categories/bulk-create/', views.CategoryBulkCreateView.as_view(), name='category-bulk-create'),
    path('categories/multiple-delete/', views.CategoryMultipleDeleteView.as_view(), name='category-multiple-delete'),
    path('categories/set/ordering/', views.CategorySetOrderingView.as_view(), name='category-set-ordering'),
    path('categories/<int:pk>/', views.CategoryDetailView.as_view(), name='category-detail'),

    # ---- ProductModels ----
    path('product-models/', views.ProductModelListCreateView.as_view(), name='product-model-list'),
    path('product-models/get-multiple/', views.ProductModelGetMultipleView.as_view(), name='product-model-get-multiple'),
    path('product-models/multiple-delete/', views.ProductModelMultipleDeleteView.as_view(), name='product-model-multiple-delete'),
    path('product-models/<int:pk>/', views.ProductModelDetailView.as_view(), name='product-model-detail'),

    # ---- ProductPhotos ----
    path('product-photos/', views.ProductPhotoListCreateView.as_view(), name='product-photo-list'),
    path('product-photos/get-multiple/', views.ProductPhotoGetMultipleView.as_view(), name='product-photo-get-multiple'),
    path('product-photos/multiple-delete/', views.ProductPhotoMultipleDeleteView.as_view(), name='product-photo-multiple-delete'),
    path('product-photos/<int:pk>/', views.ProductPhotoDetailView.as_view(), name='product-photo-detail'),

    # ---- Favorites ----
    path('favorites/', views.FavoriteListCreateView.as_view(), name='favorite-list'),
    path('favorites/<int:pk>/', views.FavoriteDeleteView.as_view(), name='favorite-delete'),

    # ---- My Products (bulk) ----
    path('my-products/bulk-create/', views.MyProductBulkCreateView.as_view(), name='my-product-bulk-create'),
    path('my-products/bulk-update/', views.MyProductBulkUpdateView.as_view(), name='my-product-bulk-update'),
]
