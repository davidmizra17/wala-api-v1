from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "external_id", "platform", "tenant", "created")
    list_filter = ("platform", "tenant")
    search_fields = ("name", "external_id", "phone", "email")
    readonly_fields = ("id", "created", "modified")
