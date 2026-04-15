from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_inbound_message(self, message_id: int):
    """
    Background task triggered after every inbound message is persisted.

    Responsibilities (filled in as B.2/B.3/B.4 are completed):
      1. Classify intent (Query / Order / Support) via LLM.
      2. If intent is Order, extract structured items and create an Order.

    Args:
        message_id: PK of the Message record to process.
    """
    from .models import Message

    try:
        message = Message.objects.get(pk=message_id)
    except Message.DoesNotExist:
        # No point retrying if the record doesn't exist
        return

    # --- Placeholder: AI pipeline will be wired here in B.2/B.3/B.4 ---
    # intent = classify_intent(message.text)
    # if intent == 'order':
    #     extract_and_create_order(message)
