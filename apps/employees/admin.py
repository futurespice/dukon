from django.contrib import admin
from apps.employees.models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'username', 'position', 'store', 'is_active')
    list_filter = ('position', 'is_active')
    search_fields = ('first_name', 'last_name', 'username')
    raw_id_fields = ('store',)
    readonly_fields = ('token', 'created_at', 'updated_at')
    # AUDIT N+1 FIX: 'store' appears in list_display.
    # raw_id_fields only affects the edit form — list_display still lazy-loads FKs.
    list_select_related = ('store',)
