from django.urls import path

from . import views

urlpatterns = [
    path("", views.asset_list, name="home"),
    path("assets/", views.asset_list, name="asset-list"),
    path("assets/new/", views.AssetCreateView.as_view(), name="asset-create"),
    path("assets/<uuid:pk>/", views.AssetDetailView.as_view(), name="asset-detail"),
    path("assets/<uuid:pk>/edit/", views.AssetUpdateView.as_view(), name="asset-update"),
    path("assets/<uuid:pk>/check-out/", views.asset_check_out, name="asset-check-out"),
    path("assets/<uuid:pk>/check-in/", views.asset_check_in, name="asset-check-in"),
    path("assets/<uuid:pk>/set-status/", views.asset_set_status, name="asset-set-status"),
    path("assets/<uuid:pk>/label/", views.asset_label, name="asset-label"),
    path("assets/<uuid:pk>/barcode.svg", views.asset_barcode_svg, name="asset-barcode-svg"),
    path("assets/<uuid:pk>/qr.png", views.asset_qr_png, name="asset-qr-png"),
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category-create"),
    path("categories/<uuid:pk>/edit/", views.CategoryUpdateView.as_view(), name="category-update"),
    path("consumables/", views.consumable_list, name="consumable-list"),
    path("consumables/new/", views.ConsumableCreateView.as_view(), name="consumable-create"),
    path("consumables/<uuid:pk>/edit/", views.ConsumableUpdateView.as_view(), name="consumable-update"),
    path("consumables/<uuid:pk>/adjust/", views.consumable_adjust, name="consumable-adjust"),
    path("scan/", views.scan_page, name="scan-page"),
    path("scan/lookup/", views.scan_lookup, name="scan-lookup"),
]
