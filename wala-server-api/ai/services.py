from django.conf import settings

from .providers.base import ConversationContext
from .providers.gemini import GeminiProvider

HISTORY_WINDOW = 10


def get_provider_for_tenant(tenant):
    api_key = tenant.gemini_api_key or settings.GEMINI_API_KEY
    model = tenant.llm_model or settings.DEFAULT_LLM_MODEL
    return GeminiProvider(api_key=api_key, model_name=model)


def build_context(message) -> ConversationContext:
    from conversations.models import Message

    conversation = message.conversation
    tenant = conversation.tenant
    contact = conversation.contact

    history_qs = (
        Message.objects.filter(conversation=conversation)
        .exclude(pk=message.pk)
        .order_by("-created")[:HISTORY_WINDOW]
    )
    history = [
        {
            "role": "user" if m.direction == Message.Direction.INBOUND else "model",
            "text": m.text,
        }
        for m in reversed(list(history_qs))
    ]
    return ConversationContext(
        business_name=tenant.name,
        bot_instructions=tenant.bot_instructions or "",
        contact_name=contact.name or contact.external_id,
        message_history=history,
        current_message=message.text,
    )


def get_ai_response(message):
    provider = get_provider_for_tenant(message.conversation.tenant)
    context = build_context(message)
    return provider.generate_response(context)
