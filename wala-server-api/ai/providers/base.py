from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConversationContext:
    business_name: str
    bot_instructions: str
    contact_name: str
    message_history: list  # list of {"role": "user"|"model", "text": str}
    current_message: str


@dataclass
class BotResponse:
    text: str
    confidence: float  # 0.0–1.0, self-assessed by the model
    should_handoff: bool = field(init=False)

    CONFIDENCE_THRESHOLD: float = 0.65

    def __post_init__(self):
        self.should_handoff = self.confidence < self.CONFIDENCE_THRESHOLD


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_response(self, context: ConversationContext) -> BotResponse: ...
