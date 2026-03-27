from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.contrib.auth import get_user_model


class IsStoreOwner(BasePermission):
    """
    Two-level permission for store ownership:
    - has_permission: ensures user is authenticated (required for list/create views)
    - has_object_permission: ensures user owns the specific object (for detail views)

    Supports direct Store objects and any related object with a .store FK.
    """
    message = 'Доступ разрешён только владельцу магазина.'

    def has_permission(self, request, view):
        # List/create views only call has_permission, not has_object_permission.
        # Ensure the user is authenticated at minimum.
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        # Direct Store object
        if hasattr(obj, 'admin_user'):
            return obj.admin_user == request.user
        # Related object (StorePhoto, Slide, StoreBankDetail, etc.)
        if hasattr(obj, 'store'):
            return obj.store.admin_user == request.user
        return False


class IsStoreOwnerOrReadOnly(BasePermission):
    """Allow safe methods (GET/HEAD/OPTIONS) to anyone, write only to store owner."""
    message = 'Доступ разрешён только владельцу магазина.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if hasattr(obj, 'admin_user'):
            return obj.admin_user == request.user
        if hasattr(obj, 'store'):
            return obj.store.admin_user == request.user
        return False


class IsVerifiedUser(BasePermission):
    """Allow only users with role != NOT_VERIFIED."""
    message = 'Подтвердите номер телефона перед использованием этой функции.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        User = get_user_model()
        return request.user.role != User.Role.NOT_VERIFIED
