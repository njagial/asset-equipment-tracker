"""Celery task: daily notification of maintenance work coming due."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import MaintenanceLog, MaintenanceStatus

logger = logging.getLogger(__name__)


def _collect_due_logs(lead_days):
    horizon = timezone.localdate() + timedelta(days=lead_days)
    return MaintenanceLog.objects.filter(
        status=MaintenanceStatus.SCHEDULED,
        scheduled_date__lte=horizon,
    ).select_related("asset")


@shared_task
def notify_due_maintenance():
    lead_days = settings.MAINTENANCE_LEAD_DAYS
    logs = list(_collect_due_logs(lead_days))
    if not logs:
        return f"No maintenance due within {lead_days} days."

    lines = []
    for log in logs:
        lines.append(
            f"- {log.asset.asset_tag} ({log.asset.name}): {log.title}, "
            f"scheduled {log.scheduled_date:%Y-%m-%d} by {log.vendor or 'internal staff'}"
        )
    send_mail(
        subject=f"[Asset Tracker] {len(logs)} maintenance task(s) due",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.NOTIFY_EMAIL],
        fail_silently=False,
    )
    logger.info("Notify due maintenance: %s items", len(logs))
    return f"Notified about {len(logs)} maintenance task(s)."
