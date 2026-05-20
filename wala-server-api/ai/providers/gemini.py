import json

import google.generativeai as genai

from .base import BaseLLMProvider, BotResponse, ConversationContext

_SYSTEM_TEMPLATE = """\
You are a helpful customer service assistant for {business_name}.
{bot_instructions}

IMPORTANT: Always reply with a single JSON object and nothing else:
{{"text": "<your reply to the customer>", "confidence": <0.0-1.0>}}

confidence reflects how certain you are that your reply fully addresses the customer's need.
Use confidence < 0.65 when the question is outside your knowledge, ambiguous, or sensitive — \
this escalates to a human agent automatically.
"""


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self._model_name = model_name

    def generate_response(self, context: ConversationContext) -> BotResponse:
        system_prompt = _SYSTEM_TEMPLATE.format(
            business_name=context.business_name,
            bot_instructions=context.bot_instructions,
        )
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )
        history = [
            {"role": m["role"], "parts": [m["text"]]}
            for m in context.message_history
        ]
        chat = model.start_chat(history=history)
        response = chat.send_message(context.current_message)
        return self._parse(response.text)

    def _parse(self, raw: str) -> BotResponse:
        try:
            # Strip markdown code fences Gemini sometimes wraps around JSON
            text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(text)
            return BotResponse(text=data["text"], confidence=float(data["confidence"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return BotResponse(text=raw.strip(), confidence=0.5)
