"""Stock watcher signals.

Fires the low-stock pipeline when a Consumable is at/below its threshold
(wired via post_save + transaction.on_commit so alerts only send for
committed rows) and auto-resolves the open alert after a restock.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.inventory.models import Consumable

from .models import LowStockAlert
from .tasks import enqueue_notify

logger = logging.getLogger(__name__)


def _process_stock_state(instance):
    open_alert = LowStockAlert.unresolved_for(instance.pk)
    if instance.is_below_threshold:
        if open_alert:
            open_alert.quantity_at_trigger = min(open_alert.quantity_at_trigger, instance.quantity_on_hand)
            open_alert.save(update_fields=["quantity_at_trigger"])
            return
        alert = LowStockAlert.objects.create(
            consumable=instance,
            quantity_at_trigger=instance.quantity_on_hand,
            threshold_at_trigger=instance.minimum_threshold,
        )
        # We are already post-commit; broker dispatch degrades gracefully.
        enqueue_notify(str(alert.pk))
    elif open_alert:
        open_alert.resolved_at = timezone.now()
        open_alert.save(update_fields=["resolved_at"])


@receiver(post_save, sender=Consumable, dispatch_uid="consumable_stock_watch")
def watch_consumable_stock(sender, instance, **kwargs):
    transaction.on_commit(lambda: _process_stock_state(instance))
