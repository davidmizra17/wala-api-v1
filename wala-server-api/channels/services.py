from django.db import transaction

from contacts.models import Contact
from conversations.models import Conversation, Message


@transaction.atomic
def register_inbound_message(channel, inbound):
    """
    Core ingest service: resolve Contact + Conversation, persist Message,
    and queue async processing.

    Deduplication: if a Message with the same meta_message_id already exists
    (duplicate webhook delivery), the operation is silently skipped.

    Args:
        channel: channels.Channel instance (may be None when tenant is unknown).
        inbound: channels.providers.base.InboundMessage dataclass.

    Returns:
        tuple (Contact, Conversation, Message | None)
        Message is None when the webhook was a duplicate delivery.
    """
    # Deduplication — idempotent against re-deliveries (T2)
    if inbound.meta_message_id:
        try:
            existing = Message.objects.select_related(
                "conversation__contact"
            ).get(meta_message_id=inbound.meta_message_id)
            return existing.conversation.contact, existing.conversation, None
        except Message.DoesNotExist:
            pass

    tenant = channel.tenant if channel else None

    # Resolve or create Contact
    contact, _ = Contact.objects.get_or_create(
        tenant=tenant,
        external_id=inbound.external_id,
        defaults={
            "name": inbound.name or f"Contact {inbound.external_id[-4:]}",
            "platform": inbound.platform,
        },
    )
    if inbound.name and contact.name != inbound.name:
        contact.name = inbound.name
        contact.save(update_fields=["name", "modified"])

    # Resolve an existing open conversation, or open a new one
    conversation = (
        Conversation.objects.filter(
            tenant=tenant,
            contact=contact,
            status__in=[
                Conversation.Status.BOT_HANDLING,
                Conversation.Status.HUMAN_HANDLING,
            ],
        )
        .order_by("-created")
        .first()
    )
    if conversation is None:
        conversation = Conversation.objects.create(
            tenant=tenant,
            contact=contact,
            channel=channel,
            status=Conversation.Status.BOT_HANDLING,
        )

    # Persist the Message
    message = Message.objects.create(
        tenant=tenant,
        conversation=conversation,
        meta_message_id=inbound.meta_message_id or None,
        text=inbound.text,
        direction=Message.Direction.INBOUND,
        sender_type=Message.SenderType.CONTACT,
        media_url=inbound.media_url,
    )

    # Queue AI processing after DB commit to avoid race conditions
    from conversations.tasks import process_inbound_message
    transaction.on_commit(lambda: process_inbound_message.delay(str(message.id)))

    return contact, conversation, message
