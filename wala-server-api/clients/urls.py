from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import WebhookIngestView

# from .views import ClientViewSet, MessageIngestView

# router = DefaultRouter()
# router.register('clients', ClientViewSet, basename='client')

urlpatterns = [
    path('webhook/', WebhookIngestView.as_view(), name='webhook-ingest'),
]

# urlpatterns += router.urls

