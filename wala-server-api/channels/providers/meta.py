import hashlib
import hmac
from typing import Optional

import requests

from .base import BaseMessagingProvider, InboundMessage

META_GRAPH_URL = "https://graph.facebook.com/v19.0"


class MetaProvider(BaseMessagingProvider):
    """
    Handles WhatsApp Business API and Instagram DM webhooks via the
    Meta Graph API.

    Both platforms share the same webhook format and the same HMAC-SHA256
    signature verification mechanism.
    """

    def __init__(self, app_secret: str):
        self._app_secret = app_secret

    # ------------------------------------------------------------------
    # Signature verification (T2)
    # ------------------------------------------------------------------

    def verify_signature(self, request) -> bool:
        signature_header = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        if not signature_header.startswith("sha256="):
            return False

        expected = (
            "sha256="
            + hmac.new(
                self._app_secret.encode(),
                request.body,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(signature_header, expected)

    # ------------------------------------------------------------------
    # Inbound payload parsing
    # ------------------------------------------------------------------

    def parse_inbound(self, payload: dict) -> Optional[InboundMessage]:
        """
        Extract the first actionable message from a Meta webhook payload.

        Meta batches multiple events per POST. We process only the first
        message entry to keep the view fast; Celery handles any deeper
        fan-out asynchronously.
        """
        try:
            entry = payload["entry"][0]
            changes = entry["changes"][0]["value"]

            # Status updates (delivered, read) — ignore
            if "statuses" in changes and "messages" not in changes:
                return None

            message = changes["messages"][0]
            contact = changes["contacts"][0]

            text = ""
            media_url = None

            if message.get("type") == "text":
                text = message["text"]["body"]
            elif message.get("type") in ("image", "audio", "video", "document"):
                media = message.get(message["type"], {})
                media_url = media.get("url", "")

            # Determine platform from the webhook object field
            platform = "whatsapp"
            if payload.get("object") == "instagram":
                platform = "instagram"

            return InboundMessage(
                external_id=message["from"],
                name=contact.get("profile", {}).get("name", ""),
                text=text,
                platform=platform,
                meta_message_id=message["id"],
                media_url=media_url,
            )
        except (KeyError, IndexError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Outbound dispatch
    # ------------------------------------------------------------------

    def send_text(self, channel, recipient_id: str, text: str) -> dict:
        url = f"{META_GRAPH_URL}/{channel.wa_phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": text},
        }
        headers = {
            "Authorization": f"Bearer {channel.wa_token}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
