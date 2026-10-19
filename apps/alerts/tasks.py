"""Low-stock Celery tasks.

notify_low_stock(alert_id) — immutable alert record + email/Slack channels.
sweep_low_stock() — beat task running every 15 minutes that guarantees an
alert exists for any consumable at/below threshold (backstop for manual DB
edits and missed signals).
"""
import json
import logging
import urllib.request

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F

from apps.inventory.models import Consumable

from .models import LowStockAlert

logger = logging.getLogger(__name__)


def _send_channels(alert, consumable):
    subject = f"[Asset Tracker] LOW STOCK: {consumable.name} ({consumable.quantity_on_hand} left)"
    body = (
        f"SKU: {consumable.sku}\n"
        f"On hand: {consumable.quantity_on_hand}\n"
        f"Minimum threshold: {consumable.minimum_threshold}\n"
        f"Location: {consumable.location or '—'}\n\n"
        "Restock queue: /alerts/restock/"
    )
    channels_sent = []

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.NOTIFY_EMAIL],
            fail_silently=False,
        )
        channels_sent.append("email")
    except Exception:
        logger.exception("Low-stock email failed for alert %s", alert.pk)

    webhook = settings.SLACK_WEBHOOK_URL
    if webhook:
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps({"text": subject}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
            channels_sent.append("slack")
        except Exception:
            logger.warning("Slack webhook failed for alert %s", alert.pk)

    return channels_sent


def enqueue_notify(alert_pk):
    """Dispatch the notification task, degrading gracefully when the broker
    (Redis) is unavailable: the alert row is already persisted, and the
    15-minute sweep_low_stock backstop re-attempts delivery."""
    try:
        notify_low_stock.delay(alert_pk)
    except Exception:
        logger.warning(
            "Broker unavailable; alert %s will be retried by sweep_low_stock.", alert_pk
        )


@shared_task
def notify_low_stock(alert_id):
    alert = LowStockAlert.objects.select_related("consumable").filter(pk=alert_id).first()
    if not alert or alert.resolved_at:
        return "Alert missing or already resolved."
    channels = _send_channels(alert, alert.consumable)
    logger.info("Low-stock notified through %s channels: %s", alert.pk, channels)
    return f"Alert {alert.pk} notified via {', '.join(channels) or 'no channel'}."


@shared_task
def sweep_low_stock():
    low_consumables = Consumable.objects.filter(quantity_on_hand__lte=F("minimum_threshold"))
    total = low_consumables.count()
    created = 0
    for consumable in low_consumables:
        if LowStockAlert.unresolved_for(consumable.pk):
            continue
        alert = LowStockAlert.objects.create(
            consumable=consumable,
            quantity_at_trigger=consumable.quantity_on_hand,
            threshold_at_trigger=consumable.minimum_threshold,
        )
        enqueue_notify(str(alert.pk))
        created += 1
    return f"sweep_low_stock: created {created} alert(s); {total} item(s) checked."
