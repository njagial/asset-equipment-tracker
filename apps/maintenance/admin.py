from django.contrib import admin

from .models import MaintenanceLog


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ("title", "asset", "maintenance_type", "status", "scheduled_date", "completed_date", "cost")
    list_filter = ("status", "maintenance_type", "is_recurring")
    search_fields = ("title", "asset__asset_tag", "asset__serial_number", "vendor")
    date_hierarchy = "scheduled_date"
    autocomplete_fields = ("asset",)


admin.site.site_header = "Asset & Equipment Tracking System Administration"
admin.site.site_title = "Asset Tracker Admin"
