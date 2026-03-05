from rest_framework import viewsets

from .models import Order
from .serializers import OrderSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """
    Standard API for Orders.
    This will be used by the Dashboard UI to list,
    update, and create orders manually.
    """
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer

