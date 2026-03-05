from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['product_name', 'quantity', 'unit_price']


class OrderSerializer(serializers.ModelSerializer):
    """
    Handles the complexity of creating an order along with its items.
    """
    items = OrderItemSerializer(many=True)
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'client', 'client_name',
            'status', 'total_amount', 'items', 'created_at'
        ]
        read_only_fields = ['order_number', 'created_at']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        return order

