from rest_framework import serializers

from .models import Client, Message

from rest_framework import serializers


class WebhookInputSerializer(serializers.Serializer):
    """
    Data Transfer Object (DTO) for incoming communication signals.

    This serializer normalizes data from different sources (WhatsApp, Instagram, Postman)
    before it reaches the service layer.
    """

    external_id = serializers.CharField(
        max_length=128,
        help_text="The unique platform identifier (e.g., phone number or Meta UID)."
    )
    text = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="The text content of the message."
    )
    platform = serializers.ChoiceField(
        choices=['whatsapp', 'instagram'],
        default='whatsapp'
    )
    media_url = serializers.URLField(
        required=False,
        allow_null=True,
        help_text="URL of the media attachment if present."
    )
    name = serializers.CharField(
        required=False,
        max_length=255,
        help_text="The display name provided by the platform webhook."
    )

    def validate_external_id(self, value):
        """
        Custom validation to ensure the ID is not just whitespace
        and follows basic sanity checks.
        """
        if not value.strip():
            raise serializers.ValidationError("external_id cannot be empty.")
        return value.strip()

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'external_id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class MessageSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    client_external_id = serializers.CharField(write_only=True)
    client_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'client',
            'client_external_id',
            'client_name',
            'text',
            'direction',
            'created_at',
        ]
        read_only_fields = ['id', 'client', 'created_at']

    def create(self, validated_data):
        external_id = validated_data.pop('client_external_id')
        client_name = validated_data.pop('client_name', '').strip()

        client, created = Client.objects.get_or_create(
            external_id=external_id,
            defaults={'name': client_name},
        )
        if not created and client_name and client.name != client_name:
            client.name = client_name
            client.save(update_fields=['name'])

        return Message.objects.create(client=client, **validated_data)

