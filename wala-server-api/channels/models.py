import uuid

from django.db import models

from common.mixins import TenantScopedModel


class Channel(TenantScopedModel):
    """
    Represents a messaging channel (WhatsApp number or Instagram account)
    configured for a specific tenant.

    Each tenant may have multiple channels across platforms.
    Credentials (wa_token) should be encrypted at rest via KMS or
    django-fernet-fields before going to production.
    """

    class Platform(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        INSTAGRAM = "instagram", "Instagram"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(
        max_length=20,
        choices=Platform.choices,
        default=Platform.WHATSAPP,
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable label (e.g. 'Main WhatsApp Line').",
    )
    # WhatsApp Business API credentials
    wa_phone_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Phone Number ID from Meta Business Manager.",
    )
    wa_token = models.CharField(
        max_length=512,
        blank=True,
        help_text="Permanent access token. Encrypt before production.",
    )
    verify_token = models.CharField(
        max_length=128,
        blank=True,
        help_text="Token used to verify Meta webhook subscriptions.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.platform})"
