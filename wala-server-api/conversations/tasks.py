from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_inbound_message(self, message_id: str):
    """
    Background task triggered after every inbound message is persisted.

    Responsibilities (filled in as AI layer is implemented):
      1. Classify intent (Query / Order / Support) via LLM.
      2. If conversation is in bot_handling state, generate and send reply.
      3. If low-confidence or sensitive topic, trigger handoff to human.

    Args:
        message_id: UUID of the conversations.Message record.
    """
    from .models import Message

    try:
        message = Message.objects.select_related("conversation").get(pk=message_id)
    except Message.DoesNotExist:
        return

    # --- AI pipeline will be wired here ---
    # intent = ai_service.classify_intent(message.text)
    # if message.conversation.status == Conversation.Status.BOT_HANDLING:
    #     response_text = ai_service.generate_response(message)
    #     send_outbound_message.delay(message.conversation_id, response_text)
