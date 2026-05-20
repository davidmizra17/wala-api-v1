import requests
from celery import shared_task
from django.conf import settings


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_inbound_message(self, message_id: str):
    """
    Background task triggered after every inbound message is persisted.

    Loads the message, calls the Gemini AI provider to generate a response,
    then either sends the bot reply or triggers auto-handoff if confidence is low.

    Args:
        message_id: UUID of the conversations.Message record.
    """
    from .models import Conversation, Message
    from .services import create_bot_outbound_message, handoff_to_agent

    try:
        message = Message.objects.select_related(
            "conversation__contact",
            "conversation__tenant",
        ).get(pk=message_id)
    except Message.DoesNotExist:
        return

    conversation = message.conversation
    if conversation.status != Conversation.Status.BOT_HANDLING:
        return  # Human already handling; don't interfere

    try:
        from ai.services import get_ai_response
        response = get_ai_response(message)
    except Exception as exc:
        raise self.retry(exc=exc)

    if response.should_handoff:
        handoff_to_agent(conversation, agent=None)
    else:
        create_bot_outbound_message(conversation, response.text)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def send_outbound_message(self, message_id: str):
    """
    Delivers an outbound message to the contact via the channel's Meta provider.

    Loads the persisted Message, calls MetaProvider.send_text(), then stores
    the platform-assigned message ID for deduplication and delivery tracking.

    Args:
        message_id: UUID of the conversations.Message record to send.
    """
    from channels.providers.meta import MetaProvider

    from .models import Message

    try:
        message = Message.objects.select_related(
            "conversation__channel",
            "conversation__contact",
        ).get(pk=message_id)
    except Message.DoesNotExist:
        return

    channel = message.conversation.channel
    contact = message.conversation.contact

    if not channel:
        return

    try:
        provider = MetaProvider(app_secret=settings.WHATSAPP_APP_SECRET)
        result = provider.send_text(channel, contact.external_id, message.text)
        meta_id = result.get("messages", [{}])[0].get("id")
        if meta_id:
            message.meta_message_id = meta_id
            message.save(update_fields=["meta_message_id"])
    except requests.HTTPError as exc:
        raise self.retry(exc=exc)
