from rest_framework import serializers

from .models import Client, Message


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

