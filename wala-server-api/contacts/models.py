import uuid

from django.db import models

from common.mixins import TenantScopedModel


class Contact(TenantScopedModel):
    """
    Represents a customer or lead who has interacted with the business
    via WhatsApp or Instagram.

    One Contact may have many Conversations across multiple sessions.
    """

    class Platform(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        INSTAGRAM = "instagram", "Instagram"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(
        max_length=128,
        help_text="Platform-assigned user ID (phone number or Meta UID).",
    )
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.WHATSAPP,
    )
    tags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="unique_contact_per_tenant",
            )
        ]

    def __str__(self) -> str:
        return self.name or self.external_id
