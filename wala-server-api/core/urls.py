from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from channels.views import WebhookIngestView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path("api/v1/auth/", include("users.urls")),
    # Core business resources
    path("api/v1/contacts/", include("contacts.urls")),
    path("api/v1/conversations/", include("conversations.urls")),
    path("api/v1/crm/", include("crm.urls")),
    path("api/v1/channels/", include("channels.urls")),
    # Meta webhook (WhatsApp + Instagram)
    path("webhooks/meta/", WebhookIngestView.as_view(), name="meta-webhook"),
    # API Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
