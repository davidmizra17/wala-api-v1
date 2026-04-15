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

    def __str__(self):
        return self.name
