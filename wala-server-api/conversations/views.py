from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Conversation
from .serializers import ConversationSerializer


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]  # no direct POST/DELETE

    def get_queryset(self):
        return (
            Conversation.objects.select_related("contact", "channel", "assigned_to")
            .prefetch_related("messages")
            .order_by("-created")
        )

    @action(detail=True, methods=["post"])
    def handoff(self, request, pk=None):
        """Transition a bot-handled conversation to human handling."""
        conversation = self.get_object()
        conversation.status = Conversation.Status.HUMAN_HANDLING
        conversation.save(update_fields=["status", "modified"])
        return Response({"status": conversation.status})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Mark a conversation as closed."""
        conversation = self.get_object()
        conversation.status = Conversation.Status.CLOSED
        conversation.save(update_fields=["status", "modified"])
        return Response({"status": conversation.status})
