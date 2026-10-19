from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.inventory.models import Asset, AssetStatus, Category
from apps.maintenance.models import MaintenanceLog, MaintenanceStatus, MaintenanceType
from apps.maintenance.tasks import notify_due_maintenance

pytestmark = pytest.mark.django_db


@pytest.fixture
def asset():
    return Asset.objects.create(
        asset_tag="AST-2026-0100",
        name="Projector",
        category=Category.objects.create(name="AV Equipment"),
        status=AssetStatus.AVAILABLE,
    )


@pytest.fixture
def users():
    return {
        "admin": User.objects.create_user("admin", password="pw", role=User.Role.ADMIN),
        "tech": User.objects.create_user("tech", password="pw", role=User.Role.TECHNICIAN),
        "viewer": User.objects.create_user("viewer", password="pw", role=User.Role.VIEWER),
    }


def _api_client(user):
    client = Client()
    client.force_login(user)
    return client


def test_maintenance_defaults(asset):
    log = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Clean air filter",
        scheduled_date=timezone.localdate() + timedelta(days=7),
    )
    assert log.status == MaintenanceStatus.SCHEDULED
    assert log.is_due is False  # scheduled in the future
    assert str(log).startswith("[Scheduled]")


def test_recurring_completion_stages_next_log(asset):
    log = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Quarterly projector service",
        scheduled_date=timezone.localdate(),
        is_recurring=True,
        recurrence_days=90,
    )
    tech = User.objects.create_user("tech", password="pw", role=User.Role.TECHNICIAN)
    log.mark_completed(tech)

    log.refresh_from_db()
    assert log.status == MaintenanceStatus.COMPLETED
    assert log.completed_date == timezone.localdate()
    nxt = MaintenanceLog.objects.exclude(pk=log.pk).get()
    assert nxt.status == MaintenanceStatus.SCHEDULED
    assert nxt.scheduled_date == log.completed_date + timedelta(days=90)


def test_completed_date_cannot_precede_scheduled(asset):
    log = MaintenanceLog(
        asset=asset,
        maintenance_type=MaintenanceType.REPAIR,
        title="Fix sprocket",
        scheduled_date=timezone.localdate(),
        completed_date=timezone.localdate() - timedelta(days=1),
    )
    with pytest.raises(ValidationError):
        log.clean()


def test_notify_due_maintenance_email(asset):
    MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.REPAIR,
        title="Bulb replacement",
        scheduled_date=timezone.localdate() + timedelta(days=2),
    )
    result = notify_due_maintenance()
    assert "1" in result
    assert len(mail.outbox) == 1
    assert "Bulb replacement" in mail.outbox[0].body


# --- Guards, views, API -------------------------------------------------------


def test_recurrence_requires_interval(asset):
    log = MaintenanceLog(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Missing interval",
        scheduled_date=timezone.localdate(),
        is_recurring=True,
        recurrence_days=None,
    )
    with pytest.raises(ValidationError):
        log.clean()


def test_is_due_property(asset):
    overdue = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.INSPECTION,
        title="Past-due inspection",
        scheduled_date=timezone.localdate() - timedelta(days=3),
    )
    future = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.INSPECTION,
        title="Future inspection",
        scheduled_date=timezone.localdate() + timedelta(days=3),
    )
    completed = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.INSPECTION,
        title="Done already",
        scheduled_date=timezone.localdate(),
        status=MaintenanceStatus.COMPLETED,
        completed_date=timezone.localdate(),
    )
    assert overdue.is_due
    assert not future.is_due
    assert not completed.is_due


def test_notify_due_maintenance_nothing_due(asset):
    before = len(mail.outbox)
    result = notify_due_maintenance()
    assert "No maintenance due" in result
    assert len(mail.outbox) == before


# --- Web views -------------------------------------------------------------------


def test_maintenance_list_requires_login():
    resp = Client().get("/maintenance/")
    assert resp.status_code == 302
    assert "/login/" in resp["Location"]


def test_maintenance_list_filters(asset, users):
    upcoming = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Quarterly filter check",
        scheduled_date=timezone.localdate() + timedelta(days=10),
    )
    done = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.REPAIR,
        title="Replaced bulb",
        scheduled_date=timezone.localdate() - timedelta(days=1),
        status=MaintenanceStatus.COMPLETED,
        completed_date=timezone.localdate(),
    )
    client = _api_client(users["viewer"])

    resp = client.get("/maintenance/", {"upcoming": "1"})
    content = resp.content.decode()
    assert "Quarterly filter check" in content
    assert "Replaced bulb" not in content

    resp = client.get("/maintenance/", {"status": MaintenanceStatus.COMPLETED})
    content = resp.content.decode()
    assert "Replaced bulb" in content
    assert "Quarterly filter check" not in content

    resp = client.get("/maintenance/", {"type": MaintenanceType.PREVENTATIVE})
    content = resp.content.decode()
    assert upcoming.title in content
    assert done.title not in content
    assert resp.status_code == 200

    resp = client.get("/maintenance/", HTTP_HX_REQUEST="true")
    assert b"<html" not in resp.content.lower()
    assert "Quarterly filter check" in resp.content.decode()


def test_maintenance_create_web(asset, users):
    client = _api_client(users["tech"])
    resp = client.post(
        "/maintenance/new/",
        {
            "asset": asset.pk,
            "maintenance_type": MaintenanceType.REPAIR,
            "title": "Clean laser window",
            "scheduled_date": "2026-11-01",
            "status": MaintenanceStatus.SCHEDULED,
        },
        follow=True,
    )
    assert resp.status_code == 200
    assert MaintenanceLog.objects.filter(title="Clean laser window").exists()
    log = MaintenanceLog.objects.get(title="Clean laser window")
    assert log.scheduled_date.isoformat() == "2026-11-01"

    resp = _api_client(users["viewer"]).post(
        "/maintenance/new/",
        {
            "asset": asset.pk,
            "maintenance_type": MaintenanceType.REPAIR,
            "title": "Nope",
            "scheduled_date": "2026-11-01",
        },
    )
    assert resp.status_code == 403
    assert not MaintenanceLog.objects.filter(title="Nope").exists()


def test_maintenance_complete_web(asset, users):
    log = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.REPAIR,
        title="Fuse replacement",
        scheduled_date=timezone.localdate(),
    )
    client = _api_client(users["tech"])
    resp = client.post(f"/maintenance/{log.pk}/complete/", {}, follow=True)
    assert resp.status_code == 200
    log.refresh_from_db()
    assert log.status == MaintenanceStatus.COMPLETED
    assert log.completed_date == timezone.localdate()
    assert log.performed_by == users["tech"]


def test_maintenance_complete_htmx_renders_row(asset, users):
    log = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Cooling fan service",
        scheduled_date=timezone.localdate(),
    )
    resp = _api_client(users["tech"]).post(f"/maintenance/{log.pk}/complete/", {}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert b"Cooling fan service" in resp.content
    assert b"<html" not in resp.content.lower()
    log.refresh_from_db()
    assert log.status == MaintenanceStatus.COMPLETED


def test_maintenance_complete_viewer_denied(asset, users):
    log = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.REPAIR,
        title="Viewer cannot complete",
        scheduled_date=timezone.localdate(),
    )
    resp = _api_client(users["viewer"]).post(f"/maintenance/{log.pk}/complete/", {})
    assert resp.status_code == 403
    log.refresh_from_db()
    assert log.status == MaintenanceStatus.SCHEDULED


# --- DRF API ---------------------------------------------------------------------


def test_api_maintenance_read_all_write_admin(asset, users):
    MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Quarterly service",
        scheduled_date=timezone.localdate() + timedelta(days=5),
    )
    client = _api_client(users["viewer"])
    resp = client.get("/api/maintenance/logs/")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["results"][0]["asset_tag"] == asset.asset_tag

    resp = client.post(
        "/api/maintenance/logs/",
        {"asset": asset.pk, "maintenance_type": "REPAIR", "title": "Denied", "scheduled_date": "2026-11-01"},
    )
    assert resp.status_code == 403

    resp = _api_client(users["admin"]).post(
        "/api/maintenance/logs/",
        {
            "asset": asset.pk,
            "maintenance_type": "REPAIR",
            "title": "Admin created",
            "scheduled_date": "2026-11-01",
            "status": "SCHEDULED",
        },
    )
    assert resp.status_code == 201
    assert MaintenanceLog.objects.filter(title="Admin created").exists()


def test_api_maintenance_completed_date_validation(asset, users):
    resp = _api_client(users["admin"]).post(
        "/api/maintenance/logs/",
        {
            "asset": asset.pk,
            "maintenance_type": "REPAIR",
            "title": "Impossible ordering",
            "scheduled_date": "2026-11-01",
            "completed_date": "2026-10-01",
        },
    )
    assert resp.status_code == 400
    assert "completed_date" in resp.json()


def test_api_maintenance_filterset(asset, users):
    scheduled = MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.PREVENTATIVE,
        title="Scheduled preventative",
        scheduled_date=timezone.localdate() + timedelta(days=5),
    )
    MaintenanceLog.objects.create(
        asset=asset,
        maintenance_type=MaintenanceType.REPAIR,
        title="Finished repair",
        scheduled_date=timezone.localdate(),
        status=MaintenanceStatus.COMPLETED,
        completed_date=timezone.localdate(),
    )
    client = _api_client(users["tech"])
    resp = client.get("/api/maintenance/logs/", {"status": "SCHEDULED", "maintenance_type": "PREVENTATIVE"})
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == scheduled.title

    resp = client.get("/api/maintenance/logs/", {"ordering": "-scheduled_date"})
    titles = [row["title"] for row in resp.json()["results"]]
    assert titles[0] == "Scheduled preventative"  # latest scheduled_date first
    assert titles[-1] == "Finished repair"
