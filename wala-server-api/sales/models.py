from django.db import models
import uuid


class Order(models.Model):
    """
    Represents a commercial transaction initiated via Wala.

    Status Flow:
    NEW -> CONTACTED -> PAID -> SHIPPED
    """
    STATUS_CHOICES = (
        ('NEW', 'Nuevo'),
        ('CONTACTED', 'Contactado'),
        ('PAID', 'Pagado / Confirmado'),
        ('SHIPPED', 'En Camino / Entregado'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    client = models.ForeignKey('clients.Client', on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Context for the entrepreneur
    internal_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Simple logic to generate a human-readable order number
        if not self.order_number:
            last_order = Order.objects.all().order_by('id').last()
            new_id = (last_order.id + 1) if last_order else 1
            self.order_number = f"WALA-{new_id:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} - {self.client.name}"


class OrderItem(models.Model):
    """
    Represents individual products within an order.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product_name = models.CharField(max_length=255)  # Simplified for MVP
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"
