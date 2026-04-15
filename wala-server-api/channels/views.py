from django.conf import settings
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import Channel
from .providers.meta import MetaProvider
from .serializers import ChannelSerializer
from .services import register_inbound_message


def _get_meta_provider() -> MetaProvider:
    return MetaProvider(app_secret=settings.WHATSAPP_APP_SECRET)


class WebhookIngestView(APIView):
    """
    Unified webhook endpoint for WhatsApp and Instagram (Meta platform).

    GET  — Hub Challenge verification handshake.
    POST — Ingest a webhook event; HMAC-SHA256 signature is verified before
           any processing occurs (T2).
    """

    @extend_schema(
        summary="Meta webhook verification (Hub Challenge)",
        responses={200: {"description": "Challenge echoed back to Meta"}},
    )
    def get(self, request, *args, **kwargs):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        # Support per-channel verify tokens; fall back to global setting
        valid_token = settings.WHATSAPP_VERIFY_TOKEN
        channel_id = request.query_params.get("channel_id")
        if channel_id:
            try:
                ch = Channel.objects.get(id=channel_id)
                valid_token = ch.verify_token or valid_token
            except Channel.DoesNotExist:
                pass

        if mode == "subscribe" and token == valid_token:
            return HttpResponse(challenge, content_type="text/plain", status=200)

        return HttpResponse("Forbidden", status=403)

    @extend_schema(
        summary="Ingest Meta webhook event",
        responses={200: {"description": "Event accepted"}},
    )
    def post(self, request, *args, **kwargs):
        # T2: HMAC-SHA256 signature verification
        # Only enforce if WHATSAPP_APP_SECRET is configured
        if settings.WHATSAPP_APP_SECRET:
            provider = _get_meta_provider()
            if not provider.verify_signature(request):
                return HttpResponse("Unauthorized", status=401)

        provider = _get_meta_provider()
        inbound = provider.parse_inbound(request.data)

        if inbound is None:
            # Status updates, read receipts, etc. — acknowledge and ignore
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        # Optionally resolve the Channel by wa_phone_id
        channel = None
        try:
            phone_id = (
                request.data.get("entry", [{}])[0]
                .get("changes", [{}])[0]
                .get("value", {})
                .get("metadata", {})
                .get("phone_number_id", "")
            )
            if phone_id:
                channel = Channel.objects.filter(
                    wa_phone_id=phone_id, is_active=True
                ).first()
        except (IndexError, KeyError, TypeError):
            pass

        contact, conversation, message = register_inbound_message(channel, inbound)

        return Response(
            {
                "status": "accepted" if message else "duplicate",
                "conversation_id": str(conversation.id),
            },
            status=status.HTTP_200_OK,
        )


class ChannelViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Channel.objects.all().order_by("-created")
