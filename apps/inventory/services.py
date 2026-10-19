"""Business logic for the check-in / check-out workflow.

Domain services are kept out of views so HTMX flows, DRF endpooints and the
scanned workflow all mutate state through the same audited code path.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Asset, AssetStatus, AssetTransaction, TransactionAction


def _log_txn(asset, action, performed_by, assigned_to=None, notes=""):
    AssetTransaction.objects.create(
        asset=asset,
        action=action,
        performed_by=performed_by,
        assigned_to=assigned_to,
        notes=notes,
    )


@transaction.atomic
def check_out_asset(asset_id, user, assigned_to, notes=""):
    """Check an AVAILABLE asset out to a user; logs a CHECK_OUT transaction."""
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    if asset.status != AssetStatus.AVAILABLE:
        raise ValidationError(
            f"Asset is {asset.get_status_display()} and cannot be checked out."
        )
    asset.status = AssetStatus.CHECKED_OUT
    asset.assigned_to_user = assigned_to
    asset.save(update_fields=["status", "assigned_to_user", "updated_at"])
    _log_txn(asset, TransactionAction.CHECK_OUT, user, assigned_to=assigned_to, notes=notes)
    return asset


@transaction.atomic
def check_in_asset(asset_id, user, notes="", new_location=None):
    """Return a checked-out asset to the pool; logs CHECK_IN + location move."""
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    if asset.status != AssetStatus.CHECKED_OUT:
        raise ValidationError(
            f"Asset is {asset.get_status_display()}; only checked-out assets can be checked in."
        )
    asset.status = AssetStatus.AVAILABLE
    asset.assigned_to_user = None
    if new_location and new_location != asset.location:
        asset.location = new_location
        asset.save(update_fields=["status", "assigned_to_user", "location", "updated_at"])
        _log_txn(asset, TransactionAction.LOCATION_TRANSFER, user, notes=f"Returned to {new_location}")
    else:
        asset.save(update_fields=["status", "assigned_to_user", "updated_at"])
    _log_txn(asset, TransactionAction.CHECK_IN, user, notes=notes)
    return asset


@transaction.atomic
def set_asset_status(asset_id, user, new_status, notes=""):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    if asset.status == new_status:
        return asset
    old_status = asset.status
    asset.status = new_status
    if new_status != AssetStatus.CHECKED_OUT:
        asset.assigned_to_user = None
    asset.save(update_fields=["status", "assigned_to_user", "updated_at"])
    _log_txn(
        asset,
        TransactionAction.STATUS_CHANGE,
        user,
        notes=f"{old_status} → {new_status}. {notes}".strip(),
    )
    return asset
