from django.contrib import admin

from .models import Channel


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "is_active", "tenant", "created")
    list_filter = ("platform", "is_active", "tenant")
    search_fields = ("name", "wa_phone_id")
    readonly_fields = ("id", "created", "modified")
