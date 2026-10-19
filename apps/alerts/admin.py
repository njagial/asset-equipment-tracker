from django.contrib import admin

from .models import LowStockAlert


@admin.register(LowStockAlert)
class LowStockAlertAdmin(admin.ModelAdmin):
    list_display = ("consumable", "quantity_at_trigger", "threshold_at_trigger", "created_at", "resolved_at")
    list_filter = ("consumable__category",)
    search_fields = ("consumable__name", "consumable__sku")
    list_select_related = ("consumable",)
    readonly_fields = ("created_at",)
