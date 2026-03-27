from django.urls import path
from apps.employees import views

urlpatterns = [
    path('', views.EmployeeListCreateView.as_view(), name='employee-list'),
    path('multiple-delete/', views.EmployeeMultipleDeleteView.as_view(), name='employee-multiple-delete'),
    path('auth/login/', views.EmployeeLoginView.as_view(), name='employee-login'),
    path('auth/logout/', views.EmployeeLogoutView.as_view(), name='employee-logout'),
    path('<int:pk>/', views.EmployeeDetailView.as_view(), name='employee-detail'),
]
