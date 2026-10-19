from django.contrib import admin

from .models import Asset, AssetTransaction, Category, Consumable


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("asset_tag", "name", "category", "status", "location", "assigned_to_user", "updated_at")
    list_filter = ("status", "category", "manufacturer")
    search_fields = ("asset_tag", "serial_number", "name", "location", "barcode_qr_data")
    autocomplete_fields = ("category", "assigned_to_user")
    readonly_fields = ("barcode_qr_data", "created_at", "updated_at")
    list_per_page = 50


@admin.register(AssetTransaction)
class AssetTransactionAdmin(admin.ModelAdmin):
    list_display = ("asset", "action", "performed_by", "assigned_to", "timestamp")
    list_filter = ("action",)
    search_fields = ("asset__asset_tag", "asset__serial_number", "asset__name")
    readonly_fields = ("asset", "action", "performed_by", "assigned_to", "notes", "timestamp")

    def has_add_permission(self, request):
        return False  # audit trail is written by domain services only

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Consumable)
class ConsumableAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "quantity_on_hand", "minimum_threshold", "location")
    list_filter = ("category",)
    search_fields = ("name", "sku", "location")
    autocomplete_fields = ("category",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name", "description")
