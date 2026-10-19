from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from apps.accounts.permissions import min_role

from .forms import MaintenanceLogForm
from .models import MaintenanceLog, MaintenanceStatus, MaintenanceType


def _guard(request):
    if not min_role("TECHNICIAN", "ADMIN")(request.user):
        raise PermissionDenied


class TechRequiredMixin(LoginRequiredMixin):
    """Login required + Technician/Admin gates for write endpoints."""

    def dispatch(self, request, *args, **kwargs):
        _guard(request)
        return super().dispatch(request, *args, **kwargs)


@login_required
def maintenance_list(request):
    qs = MaintenanceLog.objects.select_related("asset", "performed_by")
    status = request.GET.get("status", "")
    mtype = request.GET.get("type", "")
    if status:
        qs = qs.filter(status=status)
    if mtype:
        qs = qs.filter(maintenance_type=mtype)
    upcoming_only = request.GET.get("upcoming") == "1"
    if upcoming_only:
        qs = qs.filter(status=MaintenanceStatus.SCHEDULED)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page", "1"))
    ctx = {
        "page_obj": page_obj,
        "status": status,
        "mtype": mtype,
        "upcoming_only": upcoming_only,
        "statuses": MaintenanceStatus.choices,
        "types": MaintenanceType.choices,
        "result_count": paginator.count,
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "maintenance/partials/log_rows.html", ctx)
    return render(request, "maintenance/maintenance_list.html", ctx)


class MaintenanceCreateView(TechRequiredMixin, CreateView):
    model = MaintenanceLog
    form_class = MaintenanceLogForm
    template_name = "maintenance/maintenance_form.html"
    success_url = reverse_lazy("maintenance-list")

    def form_valid(self, form):
        messages.success(self.request, "Maintenance log created.")
        return super().form_valid(form)


class MaintenanceUpdateView(TechRequiredMixin, UpdateView):
    model = MaintenanceLog
    form_class = MaintenanceLogForm
    template_name = "maintenance/maintenance_form.html"
    success_url = reverse_lazy("maintenance-list")

    def form_valid(self, form):
        messages.success(self.request, "Maintenance log updated.")
        return super().form_valid(form)


@require_POST
def maintenance_complete(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"{reverse_lazy('login')}?next={request.path}")
    _guard(request)
    log = get_object_or_404(MaintenanceLog, pk=pk)
    cost = request.POST.get("cost") or None
    log.mark_completed(request.user, cost=cost)
    messages.success(request, f"{log.title} completed.")
    if request.headers.get("HX-Request") == "true":
        return render(request, "maintenance/partials/log_row.html", {"log": log})
    return redirect("maintenance-list")
