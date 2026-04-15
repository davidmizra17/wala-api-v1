import uuid

from django.conf import settings
from django.db import models

from common.mixins import TenantScopedModel


class Conversation(TenantScopedModel):
    """
    A thread of messages between a Contact and the business.

    Status machine:
        bot_handling  — AI bot is responding automatically
        human_handling — An agent has taken over
        closed         — Resolved/archived
    """

    class Status(models.TextChoices):
        BOT_HANDLING = "bot_handling", "Bot Handling"
        HUMAN_HANDLING = "human_handling", "Human Handling"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    channel = models.ForeignKey(
        "channels.Channel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.BOT_HANDLING,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_conversations",
    )

    def __str__(self) -> str:
        return f"Conversation({self.contact}, {self.status})"


class Message(TenantScopedModel):
    """
    A single message within a Conversation.

    meta_message_id stores the platform-assigned ID used to deduplicate
    webhook re-deliveries (T2).
    """

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class SenderType(models.TextChoices):
        CONTACT = "contact", "Contact"
        HUMAN = "human", "Human Agent"
        BOT = "bot", "Bot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    meta_message_id = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        help_text="Platform-assigned message ID used for deduplication.",
    )
    text = models.TextField(blank=True)
    direction = models.CharField(
        max_length=16,
        choices=Direction.choices,
        default=Direction.INBOUND,
    )
    sender_type = models.CharField(
        max_length=10,
        choices=SenderType.choices,
        default=SenderType.CONTACT,
    )
    media_url = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self) -> str:
        return f"Message({self.direction}, {self.conversation_id})"
