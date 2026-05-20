from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Conversation, Message


def create_outbound_message(conversation: Conversation, text: str, sender) -> Message:
    if conversation.status == Conversation.Status.CLOSED:
        raise ValidationError("Cannot send a message to a closed conversation.")

    message = Message.objects.create(
        tenant=conversation.tenant,
        conversation=conversation,
        text=text,
        direction=Message.Direction.OUTBOUND,
        sender_type=Message.SenderType.HUMAN,
    )

    transaction.on_commit(
        lambda: _dispatch_send(str(message.id))
    )
    return message


def create_bot_outbound_message(conversation: Conversation, text: str) -> Message:
    if conversation.status == Conversation.Status.CLOSED:
        return None

    message = Message.objects.create(
        tenant=conversation.tenant,
        conversation=conversation,
        text=text,
        direction=Message.Direction.OUTBOUND,
        sender_type=Message.SenderType.BOT,
    )
    transaction.on_commit(lambda: _dispatch_send(str(message.id)))
    return message


def _dispatch_send(message_id: str):
    from .tasks import send_outbound_message
    send_outbound_message.delay(message_id)


def handoff_to_agent(conversation: Conversation, agent=None) -> Conversation:
    if conversation.status != Conversation.Status.BOT_HANDLING:
        raise ValidationError(
            f"Cannot hand off a conversation with status '{conversation.status}'. "
            "Only 'bot_handling' conversations can be handed off."
        )
    conversation.status = Conversation.Status.HUMAN_HANDLING
    conversation.assigned_to = agent
    conversation.save(update_fields=["status", "assigned_to", "modified"])
    return conversation


def return_to_bot(conversation: Conversation) -> Conversation:
    if conversation.status != Conversation.Status.HUMAN_HANDLING:
        raise ValidationError(
            f"Cannot return a conversation with status '{conversation.status}' to bot. "
            "Only 'human_handling' conversations can be returned to the bot."
        )
    conversation.status = Conversation.Status.BOT_HANDLING
    conversation.assigned_to = None
    conversation.save(update_fields=["status", "assigned_to", "modified"])
    return conversation


def close_conversation(conversation: Conversation) -> Conversation:
    if conversation.status == Conversation.Status.CLOSED:
        raise ValidationError("Conversation is already closed.")
    conversation.status = Conversation.Status.CLOSED
    conversation.save(update_fields=["status", "modified"])
    return conversation
