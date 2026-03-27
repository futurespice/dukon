from django.contrib import admin
from django.utils.html import format_html

from apps.orders.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ('product',)
    readonly_fields = (
        'price_at_order',
        'product_name_at_order',
        'subtotal_display',
        'created_at',
    )
    fields = (
        'product',
        'product_name_at_order',
        'quantity',
        'price_at_order',
        'subtotal_display',
    )

    @admin.display(description='Сумма')
    def subtotal_display(self, obj):
        if obj.pk:
            return f'{obj.subtotal:.2f}'
        return '—'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'first_name', 'last_name', 'phone_number',
        'order_status', 'delivery_status', 'payment_status',
        'total_price_display', 'created_at',
    )
    list_filter = (
        'order_status', 'delivery_status', 'payment_status',
        'payment_type', 'delivery_type',
    )
    search_fields = ('phone_number', 'first_name', 'last_name', 'address')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at', 'total_price_display')
    inlines = [OrderItemInline]

    fieldsets = (
        ('Клиент', {
            'fields': ('user', 'first_name', 'last_name', 'phone_number'),
        }),
        ('Доставка', {
            'fields': ('delivery_type', 'address', 'comment'),
        }),
        ('Оплата', {
            'fields': ('payment_type', 'check_photo'),
        }),
        ('Статусы', {
            'fields': ('order_status', 'delivery_status', 'payment_status', 'notifications_sent'),
        }),
        ('Итог', {
            'fields': ('total_price_display',),
        }),
        ('Служебное', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        # AUDIT N+1 FIX: prefetch order items so total_price_display does not
        # issue a separate SELECT for each row in the changelist.
        # Without this, 20 orders in the list → 20 extra "SELECT * FROM order_items
        # WHERE order_id = ?" queries, one per row.
        qs = super().get_queryset(request)
        return qs.prefetch_related('items')

    @admin.display(description='Сумма заказа')
    def total_price_display(self, obj):
        # total_price uses self.items.all() — hits the prefetch cache, zero extra SQL.
        total = obj.total_price
        return format_html('<strong>{:.2f} сом</strong>', total)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'order', 'product_name_at_order',
        'quantity', 'price_at_order', 'subtotal_display',
    )
    readonly_fields = (
        'price_at_order',
        'product_name_at_order',
        'subtotal_display',
        'created_at',
        'updated_at',
    )
    raw_id_fields = ('order', 'product')
    search_fields = ('product_name_at_order', 'order__id')
    # AUDIT N+1 FIX: select_related for order to avoid per-row FK fetch in list_display.
    list_select_related = ('order',)

    @admin.display(description='Сумма')
    def subtotal_display(self, obj):
        return f'{obj.subtotal:.2f}'
