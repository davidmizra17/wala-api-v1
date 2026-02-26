from .models import Client, Message
from django.db import transaction

@transaction.atomic
def register_interaction(external_id, text, direction='inbound', platform='whatsapp', media_url=None, name=None):
    """
        Orchestrates the identification of a client and the persistence of their message.

        What it does:
        Ensures that every incoming or outgoing interaction is linked to a unique Client
        record. If the client does not exist, it creates one on the fly.

        How it does it:
        1. Uses 'get_or_create' with the external_id to maintain idempotency.
        2. Wraps the process in a database transaction to ensure data integrity.
        3. Defaults to a placeholder name if the platform doesn't provide one.

        Why it does it:
        To support the 'Wala' core value of zero-manual-input. Entrepreneurs should
        see their CRM populated automatically as soon as a customer reaches out.

        Args:
            external_id (str): The unique identifier from the platform (Phone or Meta ID).
            text (str): The content of the message.
            direction (str): Either 'inbound' (from client) or 'outbound' (from Wala).
            platform (str): The source of the message (whatsapp/instagram).
            media_url (str, optional): Link to hosted media files.
            name (str, optional): The client's display name if available.

        Returns:
            tuple: (Client instance, Message instance)
        """

    # 1. Lógica get_or_create para el Cliente
    # Si es nuevo, le asignamos un nombre temporal basado en su ID
    client, created = Client.objects.get_or_create(
        external_id=external_id,
        defaults={
            'name': name or f"Cliente {external_id[-4:]}"
        }
    )

    # 2. Creación del mensaje vinculado al cliente
    message = Message.objects.create(
        client=client,
        text=text,
        direction=direction,
        platform=platform,
        media_url=media_url,
        is_read=False if direction == 'inbound' else True
    )

    return client, message