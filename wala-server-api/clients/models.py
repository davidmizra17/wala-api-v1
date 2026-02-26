from django.db import models


class Client(models.Model):
    external_id = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name or self.external_id


class Message(models.Model):
    DIRECTION_CHOICES = (
        ('inbound', 'inbound'),
        ('outbound', 'outbound'),
    )

    PLATFORM_CHOICES = (
        ('whatsapp', 'WhatsApp'),
        ('instagram', 'Instagram'),
    )

    client = models.ForeignKey(Client, related_name='messages', on_delete=models.CASCADE)
    text = models.TextField()
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES, default='inbound')
    is_read = models.BooleanField(default=False)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='whatsapp')
    media_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.client} ({self.direction})"

