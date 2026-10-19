import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.accounts.models import User
from apps.inventory.barcodes import code128_png, code128_svg, qr_png_base64
from apps.inventory.models import (
    Asset,
    AssetStatus,
    AssetTransaction,
    Category,
    Consumable,
    TransactionAction,
)
from apps.inventory.search import fuzzy_search_queryset
from apps.inventory.services import check_in_asset, check_out_asset, set_asset_status
from apps.inventory.views import AssetCreateView

pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(name="AV Equipment")


@pytest.fixture
def asset(category):
    return Asset.objects.create(
        asset_tag="AST-2026-0001",
        name="Projector EPSON-100",
        category=category,
        serial_number="SN-0001",
        location="Room 204",
        custom_fields={"voltage": "220V"},
    )


@pytest.fixture
def users():
    admin = User.objects.create_user("admin", password="pw", role=User.Role.ADMIN)
    tech = User.objects.create_user("tech", password="pw", role=User.Role.TECHNICIAN)
    viewer = User.objects.create_user("viewer", password="pw", role=User.Role.VIEWER)
    return {"admin": admin, "tech": tech, "viewer": viewer}


def test_asset_defaults_and_repr(asset):
    assert asset.barcode_qr_data == f"ast:{asset.asset_tag}"
    assert str(asset).startswith("AST-2026-0001 — ")
    assert asset.is_checked_out is False


def test_consumable_below_threshold(category):
    c = Consumable.objects.create(
        name="HDMI cable 6ft", sku="HDMI-6FT", category=category, quantity_on_hand=2, minimum_threshold=5
    )
    assert c.is_below_threshold
    c.quantity_on_hand = 20
    assert not c.is_below_threshold


def test_check_out_and_audit_trail(asset, users):
    got = check_out_asset(asset.id, users["tech"], assigned_to=users["admin"], notes="studio job")
    assert got.status == AssetStatus.CHECKED_OUT
    assert got.assigned_to_user == users["admin"]
    txn = TransactionAction.CHECK_OUT
    assert AssetTransaction.objects.filter(asset=asset, action=txn).count() == 1


def test_check_out_blocked_when_not_available(asset, users):
    asset.status = AssetStatus.RETIRED
    asset.save()
    with pytest.raises(ValidationError):
        check_out_asset(asset.id, users["tech"], users["admin"])


def test_check_in_restores_availability(asset, users):
    check_out_asset(asset.id, users["tech"], users["admin"])
    check_in_asset(asset.id, users["admin"], notes="back", new_location="Rack B")
    asset.refresh_from_db()
    assert asset.status == AssetStatus.AVAILABLE
    assert asset.assigned_to_user is None
    assert asset.location == "Rack B"
    actions = list(asset.transactions.values_list("action", flat=True))
    assert TransactionAction.CHECK_IN in actions
    assert TransactionAction.LOCATION_TRANSFER in actions


def test_set_status_changes_logged(asset, users):
    set_asset_status(asset.id, users["admin"], AssetStatus.IN_MAINTENANCE, notes="fan noise")
    asset.refresh_from_db()
    assert asset.status == AssetStatus.IN_MAINTENANCE
    assert AssetTransaction.objects.filter(asset=asset, action=TransactionAction.STATUS_CHANGE).exists()


def test_fuzzy_search_fallback(asset, category):
    asset.location = "Main Warehouse"
    asset.save()
    results = fuzzy_search_queryset(Asset.objects.all(), "wareh")
    assert asset in list(results)
    results = fuzzy_search_queryset(Asset.objects.all(), "AST-2026-0001")
    assert asset in list(results)


def test_web_fuzzy_filter_paginated(asset, users):
    client = Client()
    client.force_login(users["viewer"])
    resp = client.get("/assets/", {"q": "0001"})
    assert resp.status_code == 200
    assert asset.name.encode() in resp.content


def test_viewer_cannot_create_asset(asset, users):
    client = Client()
    client.force_login(users["viewer"])
    resp = client.post("/assets/new/", {"name": "x"})
    assert resp.status_code == 403


def test_scan_lookup_resolves_payload(asset, users):
    client = Client()
    client.force_login(users["tech"])
    resp = client.post("/scan/lookup/", {"code": f"ast:{asset.asset_tag}"})
    assert resp.status_code == 200
    assert asset.asset_tag.encode() in resp.content


def test_barcodes_generate():
    svg = code128_svg("ast:TEST")
    png = code128_png("ast:TEST")
    qr = qr_png_base64("ast:TEST")
    assert svg.lstrip().startswith("<?xml") or svg.lstrip().startswith("<svg")
    assert png.startswith(b"\x89PNG")
    assert len(qr) > 100


# --- DRF API: RBAC, filtering, pagination -------------------------------------


def _api_client(user):
    client = Client()
    client.force_login(user)
    return client


def test_api_requires_authentication(asset):
    resp = Client().get("/api/inventory/assets/")
    assert resp.status_code == 403


def test_api_assets_readable_by_any_role(asset, users):
    resp = _api_client(users["viewer"]).get("/api/inventory/assets/")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 1
    row = payload["results"][0]
    assert row["asset_tag"] == asset.asset_tag
    assert row["status_display"] == "Available"
    assert row["category_name"] == asset.category.name


def test_api_asset_writes_admin_only(asset, category, users):
    tech_client = _api_client(users["tech"])
    payload = {
        "asset_tag": "AST-2026-0099",
        "name": "Denied mixer",
        "category": category.pk,
        "status": AssetStatus.AVAILABLE,
    }
    resp = tech_client.post("/api/inventory/assets/", payload)
    assert resp.status_code == 403
    assert Asset.objects.filter(asset_tag="AST-2026-0099").exists() is False

    resp = _api_client(users["admin"]).post("/api/inventory/assets/", payload)
    assert resp.status_code == 201
    created = Asset.objects.get(asset_tag="AST-2026-0099")
    assert created.barcode_qr_data == "ast:AST-2026-0099"


def test_api_asset_patch_and_delete_admin_only(asset, users):
    tech_client = _api_client(users["tech"])
    resp = tech_client.patch(
        f"/api/inventory/assets/{asset.pk}/", {"location": "Rack Z"}, content_type="application/json"
    )
    assert resp.status_code == 403

    resp = _api_client(users["admin"]).patch(
        f"/api/inventory/assets/{asset.pk}/", {"location": "Rack Z"}, content_type="application/json"
    )
    assert resp.status_code == 200
    asset.refresh_from_db()
    assert asset.location == "Rack Z"

    resp = _api_client(users["admin"]).delete(f"/api/inventory/assets/{asset.pk}/")
    assert resp.status_code == 204


def test_api_asset_search_and_status_filters(asset, category, users):
    other = Asset.objects.create(
        asset_tag="AST-2026-0002",
        name="Audio mixer X",
        category=category,
        status=AssetStatus.RETIRED,
    )
    client = _api_client(users["tech"])

    resp = client.get("/api/inventory/assets/", {"search": "0002"})
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["asset_tag"] == other.asset_tag

    resp = client.get("/api/inventory/assets/", {"status": AssetStatus.RETIRED})
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["name"] == other.name

    resp = client.get("/api/inventory/assets/", {"search": "does-not-exist-anywhere"})
    assert resp.json()["count"] == 0


def test_api_assets_paginated(category, users):
    Asset.objects.bulk_create(
        [
            Asset(asset_tag=f"AST-2026-{i:04d}", name=f"Bulk asset {i}", category=category)
            for i in range(1, 31)
        ]
    )
    resp = _api_client(users["viewer"]).get("/api/inventory/assets/")
    payload = resp.json()
    assert payload["count"] == 30
    assert len(payload["results"]) == 25
    assert payload["next"] is not None


def test_api_transactions_read_only_audit(asset, users):
    check_out_asset(asset.id, users["tech"], assigned_to=users["admin"], notes="api audit")
    client = _api_client(users["viewer"])

    resp = client.post("/api/inventory/transactions/", {})
    assert resp.status_code == 405

    resp = client.get(
        "/api/inventory/transactions/", {"asset": asset.pk, "action": TransactionAction.CHECK_OUT}
    )
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["results"][0]["performed_by"] == users["tech"].username
    assert payload["results"][0]["assigned_to"] == users["admin"].username


def test_api_consumables_filters_and_writes(category, users):
    low = Consumable.objects.create(
        name="HDMI 3ft", sku="HDMI-3FT", category=category, quantity_on_hand=2, minimum_threshold=5
    )
    Consumable.objects.create(
        name="HDMI 15ft", sku="HDMI-15FT", category=category, quantity_on_hand=48, minimum_threshold=5
    )
    client = _api_client(users["tech"])

    resp = client.get("/api/inventory/consumables/", {"below_threshold": "1"})
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["results"][0]["sku"] == low.sku
    assert payload["results"][0]["below_threshold"] is True

    resp = client.post(
        "/api/inventory/consumables/",
        {"name": "USB-C cable", "sku": "USBC-1M", "category": category.pk},
    )
    assert resp.status_code == 403

    resp = _api_client(users["admin"]).post(
        "/api/inventory/consumables/",
        {"name": "USB-C cable", "sku": "USBC-1M", "category": category.pk, "minimum_threshold": 4},
    )
    assert resp.status_code == 201
    assert resp.json()["below_threshold"] is True  # qty 0 <= threshold 4


def test_api_categories_read_all_write_admin(category, users):
    client = _api_client(users["viewer"])
    resp = client.get("/api/inventory/categories/")
    assert resp.status_code == 200

    resp = client.post("/api/inventory/categories/", {"name": "Nope"})
    assert resp.status_code == 403

    resp = _api_client(users["admin"]).post("/api/inventory/categories/", {"name": "Printers"})
    assert resp.status_code == 201


# --- Web flows: HTMX check-out / check-in / set-status --------------------------


def test_web_check_out_and_check_in_cycle(asset, users):
    client = _api_client(users["admin"])

    resp = client.post(
        f"/assets/{asset.pk}/check-out/",
        {"assigned_to": users["tech"].pk, "notes": "field job"},
        follow=True,
    )
    assert resp.status_code == 200
    asset.refresh_from_db()
    assert asset.status == AssetStatus.CHECKED_OUT
    assert asset.assigned_to_user == users["tech"]
    assert asset.transactions.filter(action=TransactionAction.CHECK_OUT).count() == 1

    resp = client.post(
        f"/assets/{asset.pk}/check-in/", {"new_location": "Room 101", "notes": "back"}, follow=True
    )
    assert resp.status_code == 200
    asset.refresh_from_db()
    assert asset.status == AssetStatus.AVAILABLE
    assert asset.assigned_to_user is None
    assert asset.location == "Room 101"
    actions = list(asset.transactions.values_list("action", flat=True))
    assert TransactionAction.CHECK_IN in actions
    assert TransactionAction.LOCATION_TRANSFER in actions


def test_web_check_out_requires_assignee(asset, users):
    client = _api_client(users["admin"])
    resp = client.post(f"/assets/{asset.pk}/check-out/", {})
    assert resp.status_code == 302
    asset.refresh_from_db()
    assert asset.status == AssetStatus.AVAILABLE
    assert asset.transactions.count() == 0


def test_web_htmx_check_out_error_returns_partial(asset, users):
    resp = _api_client(users["admin"]).post(
        f"/assets/{asset.pk}/check-out/",
        {},
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code == 200
    assert b"This field is required." in resp.content
    assert b"<html" not in resp.content.lower()


def test_web_set_status_flow(asset, users):
    client = _api_client(users["admin"])

    resp = client.post(f"/assets/{asset.pk}/set-status/", {"status": AssetStatus.RETIRED}, follow=True)
    assert resp.status_code == 200
    asset.refresh_from_db()
    assert asset.status == AssetStatus.RETIRED

    resp = client.post(f"/assets/{asset.pk}/set-status/", {"status": "NOT-A-STATUS"}, follow=True)
    assert b"Invalid status." in resp.content
    asset.refresh_from_db()
    assert asset.status == AssetStatus.RETIRED

    resp = client.post(f"/assets/{asset.pk}/set-status/", {"status": AssetStatus.CHECKED_OUT}, follow=True)
    assert b"Use Check Out to assign the asset." in resp.content


def test_web_set_status_cleared_assignment(users, category):
    asset = Asset.objects.create(
        asset_tag="AST-2026-0777",
        name="Loaner laptop",
        category=category,
        status=AssetStatus.CHECKED_OUT,
        assigned_to_user=users["viewer"],
    )
    client = _api_client(users["tech"])
    client.post(f"/assets/{asset.pk}/set-status/", {"status": AssetStatus.IN_MAINTENANCE}, follow=True)
    asset.refresh_from_db()
    assert asset.status == AssetStatus.IN_MAINTENANCE
    assert asset.assigned_to_user is None


def test_htmx_asset_list_returns_rows_partial(asset, users):
    resp = _api_client(users["viewer"]).get("/assets/", {"q": "0001"}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert asset.asset_tag.encode() in resp.content
    assert b"<html" not in resp.content.lower()


def test_asset_detail_lists_transactions_and_badges(asset, users, category):
    check_out_asset(asset.id, users["tech"], assigned_to=users["admin"], notes="on loan")
    client = _api_client(users["viewer"])
    resp = client.get(f"/assets/{asset.pk}/")
    assert resp.status_code == 200
    assert asset.asset_tag.encode() in resp.content
    assert b"Checked Out" in resp.content


# --- Labels, QR and Code128 endpoints ------------------------------------------


def test_label_endpoint(asset, users):
    client = _api_client(users["viewer"])
    resp = client.get(f"/assets/{asset.pk}/label/")
    assert resp.status_code == 200
    assert asset.asset_tag.encode() in resp.content
    assert b"data:image/png;base64," in resp.content


def test_barcode_svg_endpoint(asset):
    resp = Client().get(f"/assets/{asset.pk}/barcode.svg")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "image/svg+xml"
    assert b"Code128" in resp.content or b"<svg" in resp.content


def test_qr_png_endpoint(asset):
    resp = Client().get(f"/assets/{asset.pk}/qr.png")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")
    assert len(resp.content) > 100


# --- Categories and consumables (web) ------------------------------------------


def test_category_create_web(category, users):
    client = _api_client(users["tech"])
    resp = client.post(
        "/categories/new/", {"name": "Cameras", "description": "Bodies and lenses"}, follow=True
    )
    assert resp.status_code == 200
    assert Category.objects.filter(name="Cameras").exists()
    assert b"Cameras" in resp.content

    resp = _api_client(users["viewer"]).post("/categories/new/", {"name": "Denied"})
    assert resp.status_code == 403


def test_category_list_requires_login():
    resp = Client().get("/categories/")
    assert resp.status_code == 302
    assert "/login/" in resp["Location"]


def test_consumable_create_and_low_only_filter(category, users):
    client = _api_client(users["tech"])
    resp = client.post(
        "/consumables/new/",
        {
            "name": "Cat6 patch cable",
            "sku": "CAT6-1M",
            "category": category.pk,
            "quantity_on_hand": 3,
            "minimum_threshold": 10,
        },
        follow=True,
    )
    assert resp.status_code == 200
    assert Consumable.objects.filter(sku="CAT6-1M").exists()

    Consumable.objects.create(
        name="Plenty HDMI", sku="HDMI-PRO", category=category, quantity_on_hand=99, minimum_threshold=5
    )
    resp = client.get("/consumables/", {"low": "1"}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert b"CAT6-1M" in resp.content
    assert b"HDMI-PRO" not in resp.content


def test_consumable_adjust_delta(category, users):
    item = Consumable.objects.create(
        name="Connectors", sku="CON-01", category=category, quantity_on_hand=10, minimum_threshold=5
    )
    client = _api_client(users["admin"])

    resp = client.post(f"/consumables/{item.pk}/adjust/", {"delta": "6"}, follow=True)
    item.refresh_from_db()
    assert item.quantity_on_hand == 16

    resp = client.post(f"/consumables/{item.pk}/adjust/", {"delta": "-99"}, follow=True)
    item.refresh_from_db()
    assert item.quantity_on_hand == 0  # clamped, never negative

    resp = client.post(f"/consumables/{item.pk}/adjust/", {"delta": "abc"}, follow=True)
    assert b"Delta must be a non-zero integer." in resp.content

    resp = client.post(f"/consumables/{item.pk}/adjust/", {"delta": "0"}, follow=True)
    assert b"Delta must be a non-zero integer." in resp.content

    resp = _api_client(users["viewer"]).post(f"/consumables/{item.pk}/adjust/", {"delta": "1"})
    assert resp.status_code == 403


# --- Auto tag generation --------------------------------------------------------


def test_next_asset_tag_sequencing(category):
    assert AssetCreateView._next_tag() == "AST-2026-0001"  # empty table -> default year
    Asset.objects.create(asset_tag="AST-2026-0001", name="Probe unit", category=category)
    Asset.objects.create(asset_tag="AST-2026-0002", name="Probe unit II", category=category)
    assert AssetCreateView._next_tag() == "AST-2026-0003"


# --- Scanner ---------------------------------------------------------------------


def test_scan_page_renders(asset, users):
    resp = _api_client(users["tech"]).get("/scan/")
    assert resp.status_code == 200
    assert b'name="code"' in resp.content


def test_scan_lookup_unknown_code(asset, users):
    client = _api_client(users["tech"])
    resp = client.post("/scan/lookup/", {"code": "ast:GHOST-1234"})
    assert resp.status_code == 200
    assert b"No asset matches" in resp.content
    assert asset.asset_tag.encode() not in resp.content
