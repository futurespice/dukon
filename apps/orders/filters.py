from django_filters import rest_framework as filters
from apps.orders.models import Order


class OrderFilter(filters.FilterSet):
    payment_type = filters.ChoiceFilter(choices=Order.PaymentType.choices)
    delivery_type = filters.ChoiceFilter(choices=Order.DeliveryType.choices)
    order_status = filters.ChoiceFilter(choices=Order.OrderStatus.choices)
    delivery_status = filters.ChoiceFilter(choices=Order.DeliveryStatus.choices)
    payment_status = filters.ChoiceFilter(choices=Order.PaymentStatus.choices)
    # Preferred filter name for store UUID.
    store = filters.UUIDFilter(
        field_name='items__product__product__store__uuid'
    )
    # Backward-compatible aliases (both point to the same field).
    items__product__store = filters.UUIDFilter(
        field_name='items__product__product__store__uuid'
    )
    items__product__product__store = filters.UUIDFilter(
        field_name='items__product__product__store__uuid'
    )

    class Meta:
        model = Order
        fields = [
            'payment_type', 'delivery_type', 'order_status',
            'delivery_status', 'payment_status',
        ]
