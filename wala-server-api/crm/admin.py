from django.contrib import admin

from .models import Deal, Order, OrderItem, Pipeline, Task


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "created")
    readonly_fields = ("id", "created", "modified")


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    readonly_fields = ("id", "created", "modified")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "stage", "contact", "value", "tenant", "created")
    list_filter = ("stage", "tenant")
    search_fields = ("title", "contact__name")
    readonly_fields = ("id", "created", "modified")
    inlines = [TaskInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "deal", "assigned_to", "due_date", "is_done")
    list_filter = ("is_done", "tenant")
    readonly_fields = ("id", "created", "modified")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "contact", "status", "total_amount", "tenant", "created")
    list_filter = ("status", "tenant")
    search_fields = ("order_number", "contact__name")
    readonly_fields = ("id", "order_number", "created", "modified")
    inlines = [OrderItemInline]
