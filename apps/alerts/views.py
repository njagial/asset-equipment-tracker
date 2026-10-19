from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.accounts.permissions import min_role
from apps.inventory.models import Consumable

from .models import LowStockAlert


def _guard(request, *roles):
    if not min_role(*roles)(request.user):
        raise PermissionDenied


class RestockQueueView(LoginRequiredMixin, ListView):
    """Dashboard of all unresolved low-stock alerts (spec 5.3)."""

    template_name = "alerts/restock_queue.html"
    context_object_name = "alerts"
    paginate_by = 25

    def get_queryset(self):
        return LowStockAlert.objects.filter(resolved_at__isnull=True).select_related(
            "consumable", "consumable__category"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["below_threshold_count"] = Consumable.objects.filter(
            quantity_on_hand__lte=F("minimum_threshold")
        ).count()
        return ctx


@require_POST
def resolve_alert(request, pk):
    """Resolve a restock item once replenished (Supervisor/Technician+)."""
    _guard(request, "TECHNICIAN", "ADMIN")
    alert = get_object_or_404(LowStockAlert, pk=pk)
    alert.resolved_at = timezone.now()
    alert.save(update_fields=["resolved_at"])
    messages.success(request, f"{alert.consumable.name} marked as resolved.")
    if request.headers.get("HX-Request") == "true":
        return render(
            request, "partials/messages.html", {"messages": messages.get_messages(request)}
        )
    return redirect("restock-queue")
