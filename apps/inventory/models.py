import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


# --- Enums -------------------------------------------------------------------
class AssetStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    CHECKED_OUT = "CHECKED_OUT", "Checked Out"
    IN_MAINTENANCE = "IN_MAINTENANCE", "In Maintenance"
    RETIRED = "RETIRED", "Retired"
    LOST = "LOST", "Lost"


class TransactionAction(models.TextChoices):
    CHECK_IN = "CHECK_IN", "Check In"
    CHECK_OUT = "CHECK_OUT", "Check Out"
    STATUS_CHANGE = "STATUS_CHANGE", "Status Change"
    LOCATION_TRANSFER = "LOCATION_TRANSFER", "Location Transfer"


# --- Models ------------------------------------------------------------------
class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Asset(models.Model):
    """Physical durable equipment (browse/install/repair lifecycle)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_tag = models.CharField(
        max_length=32,
        unique=True,
        help_text='Unique human-readable tag, e.g. "AST-2026-0012"',  # spec: unique indexed
    )
    barcode_qr_data = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Payload encoded in the QR/Code128 label (auto: 'ast:<asset_tag>')",
    )
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    serial_number = models.CharField(max_length=128, unique=True, null=True, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiration = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=AssetStatus.choices, db_index=True)
    location = models.CharField(
        max_length=255, blank=True, db_index=True, help_text='e.g. "Room 204", "Rack B"'
    )
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_assets",
    )
    custom_fields = models.JSONField(default=dict, blank=True)  # JSONB on PostgreSQL
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_tag"]
        indexes = [
            models.Index(fields=["asset_tag"], name="idx_asset_tag"),
            models.Index(fields=["serial_number"], name="idx_asset_serial"),
            models.Index(fields=["location"], name="idx_asset_location"),
            models.Index(fields=["status"], name="idx_asset_status"),
            # Composite to support hot list filters (status + location).
            models.Index(fields=["status", "location"], name="idx_asset_status_loc"),
        ]

    def save(self, *args, **kwargs):
        if not self.status:
            self.status = AssetStatus.AVAILABLE
        if not self.barcode_qr_data:
            self.barcode_qr_data = f"ast:{self.asset_tag}"
        super().save(*args, **kwargs)

    @property
    def is_checked_out(self):
        return self.status == AssetStatus.CHECKED_OUT

    @property
    def under_warranty(self):
        from django.utils import timezone

        return bool(
            self.warranty_expiration and self.warranty_expiration >= timezone.localdate()
        )

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("asset-detail", kwargs={"pk": self.pk})

    def __str__(self):
        return f"{self.asset_tag} — {self.name}"


class Consumable(models.Model):
    """Fast-depleting stock items (cables, adapters, connectors)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="consumables",
    )
    quantity_on_hand = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    minimum_threshold = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(0)],
    )
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["location"], name="idx_consumable_location"),
        ]

    @property
    def is_below_threshold(self):
        return self.quantity_on_hand <= self.minimum_threshold

    def __str__(self):
        return f"{self.name} ({self.sku})"


class AssetTransaction(models.Model):
    """Append-only audit trail. Rows are never edited or deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="transactions")
    action = models.CharField(max_length=32, choices=TransactionAction.choices, db_index=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="transactions_performed",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_received",
    )
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["asset", "timestamp"], name="idx_txn_asset_ts"),
            models.Index(fields=["action"], name="idx_txn_action"),
        ]

    def __str__(self):
        return f"{self.asset.asset_tag} · {self.action} · {self.timestamp:%Y-%m-%d %H:%M}"
