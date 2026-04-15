from rest_framework import serializers

from .models import Channel


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = [
            "id",
            "platform",
            "name",
            "wa_phone_id",
            "verify_token",
            "is_active",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "created", "modified"]
        # wa_token intentionally excluded from API responses
