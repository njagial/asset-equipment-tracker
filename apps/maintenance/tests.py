from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
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
