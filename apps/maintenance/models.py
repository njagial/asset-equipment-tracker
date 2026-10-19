import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MaintenanceType(models.TextChoices):
    PREVENTATIVE = "PREVENTATIVE", "Preventative"
    REPAIR = "REPAIR", "Repair"
    INSPECTION = "INSPECTION", "Inspection"
    FIRMWARE_UPDATE = "FIRMWARE_UPDATE", "Firmware Update"


class MaintenanceStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class MaintenanceLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        "inventory.Asset",
        on_delete=models.PROTECT,
        related_name="maintenance_logs",
    )
    maintenance_type = models.CharField(max_length=32, choices=MaintenanceType.choices, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_logs_performed",
    )
    vendor = models.CharField(max_length=255, blank=True, help_text="External vendor, if outsourced")
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=32,
        choices=MaintenanceStatus.choices,
        default=MaintenanceStatus.SCHEDULED,
        db_index=True,
    )
    is_recurring = models.BooleanField(default=False)
    recurrence_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For recurring preventative work: auto-stage the next log N days after completion.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_date"]
        indexes = [
            models.Index(fields=["asset", "status"], name="idx_maint_asset_status"),
            models.Index(fields=["scheduled_date"], name="idx_maint_sched"),
        ]

    def clean(self):
        if self.completed_date and self.scheduled_date and self.completed_date < self.scheduled_date:
            raise ValidationError({"completed_date": "Completed date cannot precede the scheduled date."})
        if self.is_recurring and not self.recurrence_days:
            raise ValidationError({"recurrence_days": "Recurring logs require a recurrence interval."})

    @property
    def is_due(self):
        return self.status == MaintenanceStatus.SCHEDULED and self.scheduled_date <= timezone.localdate()

    def mark_completed(self, user, completed_date=None, cost=None):
        self.status = MaintenanceStatus.COMPLETED
        self.performed_by = user
        self.completed_date = completed_date or timezone.localdate()
        if cost is not None:
            self.cost = cost
        self.save(update_fields=["status", "performed_by", "completed_date", "cost", "updated_at"])
        if self.is_recurring and self.recurrence_days:
            MaintenanceLog.objects.create(
                asset=self.asset,
                maintenance_type=self.maintenance_type,
                title=self.title,
                description=self.description,
                scheduled_date=self.completed_date + timedelta(days=self.recurrence_days),
                is_recurring=True,
                recurrence_days=self.recurrence_days,
            )

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title} · {self.asset.asset_tag}"
