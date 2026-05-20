import uuid
from django.db import models
from model_utils.models import TimeStampedModel


class Tenant(TimeStampedModel):
    class Subscription(models.TextChoices):
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        PRO = "pro", "Pro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    subscription = models.CharField(
        max_length=10,
        choices=Subscription.choices,
        default=Subscription.FREE,
    )
    is_active = models.BooleanField(default=True)

    # AI configuration
    bot_instructions = models.TextField(blank=True, default="")
    ai_provider = models.CharField(max_length=20, default="gemini")
    llm_model = models.CharField(max_length=100, blank=True)
    gemini_api_key = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name
