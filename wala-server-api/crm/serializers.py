from rest_framework import serializers

from .models import Deal, Order, OrderItem, Pipeline, Task


class PipelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pipeline
        fields = ["id", "name", "created", "modified"]
        read_only_fields = ["id", "created", "modified"]


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["id", "deal", "title", "due_date", "assigned_to", "is_done", "created"]
        read_only_fields = ["id", "created"]


class DealSerializer(serializers.ModelSerializer):
    # Compact contact representation for board/list views
    contact_name = serializers.CharField(source="contact.name", read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "pipeline",
            "contact",
            "contact_name",
            "title",
            "stage",
            "value",
            "conversation",
            "order",
            "tasks",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "contact_name", "created", "modified"]


class BoardColumnSerializer(serializers.Serializer):
    """One column in the Kanban board response."""
    stage = serializers.CharField()
    label = serializers.CharField()
    deals = DealSerializer(many=True)


class BoardSerializer(serializers.Serializer):
    """Full board response for a pipeline."""
    pipeline = PipelineSerializer()
    columns = BoardColumnSerializer(many=True)


# ---------------------------------------------------------------------------
# Order serializers — unchanged
# ---------------------------------------------------------------------------


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "quantity", "unit_price"]
        read_only_fields = ["id"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "contact",
            "status",
            "total_amount",
            "internal_notes",
            "items",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "order_number", "created", "modified"]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        return order
