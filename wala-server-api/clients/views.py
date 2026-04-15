from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .services import register_interaction
from .serializers import WebhookInputSerializer


class WebhookIngestView(APIView):
    """
    API View to handle incoming signals from messaging platforms.

    GET  — Meta verification handshake (Hub Challenge).
    POST — Ingest a message from WhatsApp/Instagram.
    """

    @extend_schema(
        summary="Meta webhook verification (Hub Challenge)",
        responses={200: {"description": "Challenge echoed back to Meta"}}
    )
    def get(self, request, *args, **kwargs):
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')

        if mode == 'subscribe' and token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge, content_type='text/plain', status=200)

        return HttpResponse('Forbidden', status=403)

    @extend_schema(
        summary="Ingest message from platform",
        request=WebhookInputSerializer,
        responses={201: {"description": "Interaction recorded successfully"}}
    )
    def post(self, request, *args, **kwargs):
        # 1. Validation (The Contract)
        serializer = WebhookInputSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.validated_data

            # 2. Business Logic (The Service Layer)
            # We use the service to ensure atomicity and decoupling
            client, message = register_interaction(
                external_id=data['external_id'],
                text=data.get('text'),
                platform=data.get('platform', 'whatsapp'),
                media_url=data.get('media_url'),
                name=data.get('name')
            )

            return Response(
                {
                    "status": "success",
                    "client_id": client.external_id,
                    "message_id": message.id
                },
                status=status.HTTP_201_CREATED
            )

        # 3. Error Handling
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

