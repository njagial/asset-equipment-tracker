import uuid

from django.db import models


class LowStockAlert(models.Model):
    """Persisted representation of a low-stock trigger event.

    At most one *unresolved* alert per consumable (guarded by a partial unique
    constraint) so restocks converge rather than spam duplicates. Each alert
    snapshots quantity/threshold at trigger time for audit purposes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consumable = models.ForeignKey(
        "inventory.Consumable",
        on_delete=models.CASCADE,
        related_name="low_stock_alerts",
    )
    quantity_at_trigger = models.PositiveIntegerField()
    threshold_at_trigger = models.PositiveIntegerField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["consumable", "resolved_at"], name="idx_alert_cons_resolved"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["consumable"],
                condition=models.Q(resolved_at__isnull=True),
                name="uq_one_open_alert_per_consumable",
            ),
        ]

    @classmethod
    def unresolved_for(cls, consumable_id):
        return cls.objects.filter(consumable_id=consumable_id, resolved_at__isnull=True).first()

    def __str__(self):
        return f"Low stock: {self.consumable} (qty {self.quantity_at_trigger} ≤ thr {self.threshold_at_trigger})"
