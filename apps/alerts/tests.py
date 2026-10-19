import uuid

import pytest
from django.conf import settings
from django.core import mail
from django.db.utils import IntegrityError
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.alerts.models import LowStockAlert
from apps.alerts.tasks import notify_low_stock, sweep_low_stock
from apps.inventory.models import Category, Consumable

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def category():
    return Category.objects.create(name="Peripherals")


@pytest.fixture
def user():
    return User.objects.create_user("tech", password="pw", role=User.Role.TECHNICIAN)


def _make_consumable(category, qty=2, threshold=5):
    return Consumable.objects.create(
        name="USB-C dongle",
        sku="USBC-DONGLE",
        category=category,
        quantity_on_hand=qty,
        minimum_threshold=threshold,
        location="Drawer 3",
    )


def test_signal_creates_low_stock_alert_and_email(category):
    consumable = _make_consumable(category, qty=10, threshold=5)
    assert LowStockAlert.objects.count() == 0  # high stock: nothing

    consumable.quantity_on_hand = 2
    consumable.save(update_fields=["quantity_on_hand", "updated_at"])

    assert LowStockAlert.objects.count() == 1
    alert = LowStockAlert.objects.get()
    assert alert.quantity_at_trigger == 2
    assert alert.resolved_at is None
    assert len(mail.outbox) == 1  # Celery eager-mode ran notify_low_stock
    assert "LOW STOCK" in mail.outbox[0].subject


def test_restock_resolves_open_alert(category):
    consumable = _make_consumable(category, qty=1, threshold=5)
    alert = LowStockAlert.unresolved_for(consumable.pk)
    assert alert is not None

    consumable.quantity_on_hand = 50  # restock
    consumable.save(update_fields=["quantity_on_hand", "updated_at"])

    alert.refresh_from_db()
    assert alert.resolved_at is not None


def test_only_one_open_alert_per_consumable(category):
    consumable = _make_consumable(category, qty=1, threshold=5)
    with pytest.raises(IntegrityError):
        LowStockAlert.objects.create(  # duplicate open alert forbidden
            consumable=consumable,
            quantity_at_trigger=1,
            threshold_at_trigger=5,
        )


def test_sweep_is_idempotent_backstop(category):
    from django.db.models.signals import post_save

    from apps.alerts.signals import watch_consumable_stock

    # Simulate a stock write that slipped past the live pipeline (e.g. manual
    # DB edit / lost signal): create the row with the watcher disconnected.
    post_save.disconnect(watch_consumable_stock, sender=Consumable, dispatch_uid="consumable_stock_watch")
    try:
        consumable = _make_consumable(category, qty=0, threshold=5)
        assert LowStockAlert.unresolved_for(consumable.pk) is None

        first = sweep_low_stock()
        second = sweep_low_stock()
    finally:
        post_save.connect(watch_consumable_stock, sender=Consumable, dispatch_uid="consumable_stock_watch")

    alert = LowStockAlert.unresolved_for(consumable.pk)
    assert alert is not None, "sweep must create the missing alert"
    assert "created 1" in first
    assert "created 0" in second  # second run is a no-op


def test_restock_queue_view(category):
    user = User.objects.create_user("admin2", password="pw", role=User.Role.ADMIN)
    _make_consumable(category, qty=1, threshold=5)
    client = Client()
    client.force_login(user)
    resp = client.get("/alerts/restock/")
    assert resp.status_code == 200
    assert b"USB-C dongle" in resp.content

    alert = LowStockAlert.unresolved_for(Consumable.objects.get(sku="USBC-DONGLE").pk)
    client.post(f"/alerts/restock/{alert.pk}/resolve/")
    assert LowStockAlert.unresolved_for(alert.consumable_id) is None


def test_notify_low_stock_skips_missing_and_resolved_alerts(category):
    consumable = _make_consumable(category, qty=10, threshold=5)
    assert notify_low_stock(str(uuid.uuid4())) == "Alert missing or already resolved."

    alert = LowStockAlert.objects.create(
        consumable=consumable,
        quantity_at_trigger=1,
        threshold_at_trigger=2,
        resolved_at=timezone.now(),
    )
    assert notify_low_stock(str(alert.pk)) == "Alert missing or already resolved."
    assert len(mail.outbox) == 0


def test_notify_low_stock_email_channel(category):
    consumable = _make_consumable(category, qty=1, threshold=5)
    alert = LowStockAlert.unresolved_for(consumable.pk)

    mail.outbox.clear()  # the eager on_commit pipeline already mailed once at trigger
    result = notify_low_stock(str(alert.pk))

    assert "email" in result
    assert len(mail.outbox) == 1
    assert "LOW STOCK" in mail.outbox[0].subject
    assert "USB-C dongle" in mail.outbox[0].subject
    assert "USBC-DONGLE" in mail.outbox[0].body
    assert settings.NOTIFY_EMAIL in mail.outbox[0].to


def test_open_alert_tracks_lowest_quantity(category):
    consumable = _make_consumable(category, qty=4, threshold=5)
    alert = LowStockAlert.unresolved_for(consumable.pk)
    assert alert.quantity_at_trigger == 4

    consumable.quantity_on_hand = 1
    consumable.save(update_fields=["quantity_on_hand", "updated_at"])

    alert.refresh_from_db()
    assert alert.quantity_at_trigger == 1
    assert LowStockAlert.objects.count() == 1  # snapshot updated, no duplicate


def test_alert_str_snapshot(category):
    consumable = _make_consumable(category, qty=2, threshold=5)
    alert = LowStockAlert.unresolved_for(consumable.pk)
    alert_str = str(alert)
    assert consumable.sku in alert_str
    assert "qty 2" in alert_str
    assert "thr 5" in alert_str
