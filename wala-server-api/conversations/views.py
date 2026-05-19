from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import User

from .models import Conversation
from .serializers import ConversationSerializer, MessageSerializer, SendMessageSerializer
from .services import close_conversation, create_outbound_message, handoff_to_agent, return_to_bot


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "post", "head", "options"]  # no DELETE

    def get_queryset(self):
        return (
            Conversation.objects.select_related("contact", "channel", "assigned_to")
            .prefetch_related("messages")
            .order_by("-created")
        )

    @action(detail=True, methods=["post"], url_path="messages")
    def send_message(self, request, pk=None):
        conversation = self.get_object()
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = create_outbound_message(
            conversation=conversation,
            text=serializer.validated_data["text"],
            sender=request.user,
        )
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def handoff(self, request, pk=None):
        conversation = self.get_object()

        assigned_to_id = request.data.get("assigned_to")
        if assigned_to_id:
            try:
                agent = User.objects.get(id=assigned_to_id, tenant=request.user.tenant)
            except User.DoesNotExist:
                raise ValidationError({"assigned_to": "Agent not found in this tenant."})
        else:
            agent = request.user

        conversation = handoff_to_agent(conversation, agent)
        return Response(ConversationSerializer(conversation).data)

    @action(detail=True, methods=["post"], url_path="return_to_bot")
    def return_to_bot(self, request, pk=None):
        conversation = self.get_object()
        conversation = return_to_bot(conversation)
        return Response(ConversationSerializer(conversation).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        conversation = self.get_object()
        conversation = close_conversation(conversation)
        return Response(ConversationSerializer(conversation).data)
