from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ClientViewSet, MessageIngestView

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')

urlpatterns = [
    path('messages/ingest/', MessageIngestView.as_view(), name='message-ingest'),
]

urlpatterns += router.urls

