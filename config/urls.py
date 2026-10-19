"""Root URL configuration.

Web (HTMX) surface is served from the app url modules; DRF endpoints are
namespaced under /api/.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/inventory/", include("apps.inventory.api_urls")),
    path("api/maintenance/", include("apps.maintenance.api_urls")),
    path("maintenance/", include("apps.maintenance.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("", include("apps.inventory.urls")),
]
