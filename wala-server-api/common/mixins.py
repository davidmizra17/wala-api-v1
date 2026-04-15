from django.db import models
from model_utils.models import TimeStampedModel


class TenantScopedManager(models.Manager):
    """
    Auto-filters querysets to the current request's tenant.

    Falls back to unfiltered queryset when no tenant is set in thread-local
    context (e.g. management commands, Celery tasks, admin).  Views that need
    strict enforcement should assert `get_current_tenant() is not None`.
    """

    def get_queryset(self):
        from common.middleware import get_current_tenant

        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is not None:
            qs = qs.filter(tenant=tenant)
        return qs


class TenantScopedModel(TimeStampedModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantScopedManager()

    class Meta:
        abstract = True
