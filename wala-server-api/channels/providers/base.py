from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class InboundMessage:
    """Normalised representation of an inbound message from any platform."""

    external_id: str       # Platform user ID (phone or Meta UID)
    name: str              # Display name from platform
    text: str
    platform: str          # 'whatsapp' | 'instagram'
    meta_message_id: str   # Platform-assigned message ID (for deduplication)
    media_url: Optional[str] = None


class BaseMessagingProvider(ABC):
    """
    Abstract base for all messaging platform integrations.

    Concrete implementations (MetaProvider, etc.) handle platform-specific
    payload parsing, signature verification, and outbound message dispatch.
    """

    @abstractmethod
    def verify_signature(self, request) -> bool:
        """Return True if the webhook signature is valid."""

    @abstractmethod
    def parse_inbound(self, payload: dict) -> Optional[InboundMessage]:
        """
        Parse a raw webhook payload into an InboundMessage.
        Return None if the payload contains no actionable message
        (e.g. status updates, read receipts).
        """

    @abstractmethod
    def send_text(self, channel, recipient_id: str, text: str) -> dict:
        """
        Send a plain-text message via the platform.

        Args:
            channel:       Channel model instance (carries credentials).
            recipient_id:  Platform user ID of the recipient.
            text:          Message body.

        Returns:
            Raw API response dict.
        """
