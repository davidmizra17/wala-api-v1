import uuid

from django.conf import settings
from django.db import models

from common.mixins import TenantScopedModel


class Pipeline(TenantScopedModel):
    """
    A named sales pipeline belonging to a tenant.
    MVP: one pipeline per tenant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name


class Deal(TenantScopedModel):
    """
    A sales opportunity moving through pipeline stages.

    Stage machine (fixed for MVP):
        new → contacted → qualified → won | lost

    A Deal may link to the Conversation that originated it and to the Order
    that was created when it closed.
    """

    class Stage(models.TextChoices):
        NEW       = "new",       "New Lead"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        WON       = "won",       "Won"
        LOST      = "lost",      "Lost"

    # Fixed display order used by the board endpoint
    STAGE_ORDER = [
        Stage.NEW,
        Stage.CONTACTED,
        Stage.QUALIFIED,
        Stage.WON,
        Stage.LOST,
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name="deals",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.PROTECT,
        related_name="deals",
    )
    title = models.CharField(max_length=255)
    stage = models.CharField(
        max_length=20,
        choices=Stage.choices,
        default=Stage.NEW,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated deal value.",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deals",
    )
    order = models.OneToOneField(
        "crm.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deal",
    )

    def __str__(self) -> str:
        return f"{self.title} [{self.stage}]"


class Task(TenantScopedModel):
    """
    An agent action item attached to a Deal.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    title = models.CharField(max_length=255)
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    is_done = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.title


# ---------------------------------------------------------------------------
# Order + OrderItem — unchanged, kept here for cohesion
# ---------------------------------------------------------------------------


class Order(TenantScopedModel):
    """
    Represents a confirmed commercial transaction linked to a Contact.

    Status flow: NEW → CONTACTED → PAID → SHIPPED
    """

    class Status(models.TextChoices):
        NEW       = "NEW",       "Nuevo"
        CONTACTED = "CONTACTED", "Contactado"
        PAID      = "PAID",      "Pagado / Confirmado"
        SHIPPED   = "SHIPPED",   "En Camino / Entregado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    internal_notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            count = Order.objects.count()
            self.order_number = f"WALA-{count + 1:05d}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.order_number} - {self.contact}"


class OrderItem(models.Model):
    """Individual line item within an Order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_name}"
