from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "id",
            "meta_message_id",
            "text",
            "direction",
            "sender_type",
            "media_url",
            "created",
        ]
        read_only_fields = ["id", "meta_message_id", "created"]


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "contact",
            "channel",
            "status",
            "assigned_to",
            "messages",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "created", "modified"]
