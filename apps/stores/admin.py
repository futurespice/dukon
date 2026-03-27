from django.contrib import admin

from apps.stores.models import (
    Store, StorePhoto, BankType, StoreBankDetail,
    StoreBalanceTransaction, StoreTariffPlan, Slide, Promocode,
)


@admin.register(BankType)
class BankTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'tariff_plan', 'balance', 'cashback_percent', 'admin_user', 'created_at')
    list_filter = ('tariff_plan', 'type_of_bonus_system', 'cashback_percent')
    search_fields = ('name', 'slug', 'address', 'phone_number')
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'balance')
    raw_id_fields = ('admin_user', 'region')
    # AUDIT N+1 FIX: 'admin_user' appears in list_display.
    # raw_id_fields only affects the edit form — list_display still lazy-loads FKs.
    list_select_related = ('admin_user',)


@admin.register(StorePhoto)
class StorePhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'store', 'created_at')
    raw_id_fields = ('store',)
    # AUDIT N+1 FIX: 'store' appears in list_display.
    list_select_related = ('store',)


@admin.register(StoreBankDetail)
class StoreBankDetailAdmin(admin.ModelAdmin):
    list_display = ('store', 'bank', 'bank_account_number', 'created_at')
    raw_id_fields = ('store',)
    search_fields = ('bank_account_number', 'store__name')
    # AUDIT N+1 FIX: 'store' and 'bank' appear in list_display.
    list_select_related = ('store', 'bank')


@admin.register(StoreBalanceTransaction)
class StoreBalanceTransactionAdmin(admin.ModelAdmin):
    list_display = ('store', 'amount', 'transaction_type', 'type', 'status', 'created_at')
    list_filter = ('transaction_type', 'type', 'status')
    search_fields = ('store__name', 'description')
    raw_id_fields = ('store',)
    readonly_fields = ('created_at', 'updated_at', 'balance_before', 'balance_after')
    # AUDIT N+1 FIX: 'store' appears in list_display.
    list_select_related = ('store',)


@admin.register(StoreTariffPlan)
class StoreTariffPlanAdmin(admin.ModelAdmin):
    list_display = ('store', 'tariff_plan', 'duration_type', 'amount', 'start_date', 'end_date')
    list_filter = ('tariff_plan', 'duration_type')
    raw_id_fields = ('store',)
    readonly_fields = ('created_at', 'updated_at')
    # AUDIT N+1 FIX: 'store' appears in list_display.
    list_select_related = ('store',)


@admin.register(Slide)
class SlideAdmin(admin.ModelAdmin):
    list_display = ('store', 'title', 'sort_order', 'created_at')
    search_fields = ('title', 'store__name')
    raw_id_fields = ('store',)
    list_editable = ('sort_order',)
    # AUDIT N+1 FIX: 'store' appears in list_display.
    list_select_related = ('store',)


@admin.register(Promocode)
class PromocodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'store', 'amount', 'is_used', 'used_at', 'created_at')
    list_filter = ('is_used',)
    search_fields = ('code', 'store__name')
    raw_id_fields = ('store',)
    readonly_fields = ('used_at',)
    # AUDIT N+1 FIX: 'store' appears in list_display.
    list_select_related = ('store',)
