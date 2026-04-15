from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Contact
from .serializers import ContactSerializer


class ContactViewSet(viewsets.ModelViewSet):
    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # TenantScopedManager auto-filters by current tenant.
        # Explicit ordering applied here for consistent pagination.
        return Contact.objects.all().order_by("-created")
