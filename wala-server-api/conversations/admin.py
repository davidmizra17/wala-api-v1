from django.contrib import admin

from .models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "contact", "status", "assigned_to", "tenant", "created")
    list_filter = ("status", "tenant")
    search_fields = ("contact__name", "contact__external_id")
    readonly_fields = ("id", "created", "modified")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "direction", "sender_type", "created")
    list_filter = ("direction", "sender_type")
    search_fields = ("text", "meta_message_id")
    readonly_fields = ("id", "created", "modified")
