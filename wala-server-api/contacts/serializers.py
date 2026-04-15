from rest_framework import serializers

from .models import Contact


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = [
            "id",
            "external_id",
            "name",
            "phone",
            "email",
            "platform",
            "tags",
            "notes",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "created", "modified"]
