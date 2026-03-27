from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserBonusCard, VerificationCode


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('phone', 'first_name', 'last_name', 'role', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'gender')
    search_fields = ('phone', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)
    readonly_fields = ('date_joined', 'last_login', 'last_activity')

    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        (_('Personal info'), {
            'fields': ('first_name', 'last_name', 'middle_name', 'email', 'image',
                       'gender', 'date_of_birth')
        }),
        (_('Permissions'), {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser',
                       'groups', 'user_permissions')
        }),
        (_('Important dates'), {'fields': ('last_login', 'last_activity', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'password1', 'password2', 'role'),
        }),
    )

    # Override username field
    USERNAME_FIELD = 'phone'


@admin.register(UserBonusCard)
class UserBonusCardAdmin(admin.ModelAdmin):
    list_display = ('user', 'bonus_card_number', 'created_at')
    search_fields = ('user__phone', 'bonus_card_number')
    raw_id_fields = ('user',)


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ('phone', 'code', 'purpose', 'is_used', 'expires_at', 'created_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('phone',)
    readonly_fields = ('created_at', 'updated_at')
