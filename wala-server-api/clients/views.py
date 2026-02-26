from rest_framework import viewsets
from rest_framework.generics import CreateAPIView

from .models import Client
from .serializers import ClientSerializer, MessageSerializer


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().order_by('-created_at')
    serializer_class = ClientSerializer


class MessageIngestView(CreateAPIView):
    serializer_class = MessageSerializer

