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
    assert AssetTransaction.objects.filter(
        asset=asset, action=TransactionAction.STATUS_CHANGE
    ).exists()


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
