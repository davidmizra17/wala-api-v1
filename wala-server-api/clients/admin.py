from django.contrib import admin

from .models import Client, Message


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'name', 'created_at')
    search_fields = ('external_id', 'name')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('client', 'direction', 'created_at')
    search_fields = ('client__external_id', 'client__name', 'text')

