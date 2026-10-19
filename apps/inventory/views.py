import base64
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.permissions import min_role

from .barcodes import code128_svg, qr_png_base64
from .forms import AssetForm, CategoryForm, CheckInForm, CheckOutForm, ConsumableForm
from .models import Asset, AssetStatus, Category, Consumable
from .search import SEARCH_FIELDS, fuzzy_search_queryset
from .services import check_in_asset, check_out_asset, set_asset_status

BLOCK = "TECHNICIAN", "ADMIN"


def _guard(request, *roles):
    """Raise PermissionDenied unless the user holds one of the given roles."""
    if not min_role(*roles)(request.user):
        raise PermissionDenied


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _messages_html(request):
    return render(request, "partials/messages.html", {"messages": messages.get_messages(request)})


# --- HTMX asset list: search + filters + server-side pagination ---------------
@login_required
def asset_list(request):
    qs = Asset.objects.select_related("category", "assigned_to_user")
    term = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    category_id = request.GET.get("category", "")

    if term:
        qs = fuzzy_search_queryset(qs, term)
    if status:
        qs = qs.filter(status=status)
    if category_id:
        qs = qs.filter(category_id=category_id)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    keep = {k: v for k, v in request.GET.items() if k not in {"page"}}
    keep["page"] = "_PAGE_"
    page_query = urlencode(keep)

    ctx = {
        "page_obj": page_obj,
        "page_query": page_query,
        "search_term": term,
        "status": status,
        "category_id": category_id,
        "statuses": AssetStatus.choices,
        "categories": Category.objects.all(),
        "result_count": paginator.count,
        "search_fields": SEARCH_FIELDS,
    }
    if _htmx(request):
        return render(request, "inventory/partials/asset_rows.html", ctx)
    return render(request, "inventory/asset_list.html", ctx)


class TechRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        _guard(request, *BLOCK)
        return super().dispatch(request, *args, **kwargs)


class AssetCreateView(TechRequiredMixin, CreateView):
    model = Asset
    form_class = AssetForm
    template_name = "inventory/asset_form.html"

    def form_valid(self, form):
        form.instance.asset_tag = form.instance.asset_tag or self._next_tag()
        return super().form_valid(form)

    @staticmethod
    def _next_tag():
        year = Asset.objects.latest("created_at").created_at.year if Asset.objects.exists() else 2026
        seq = f"{Asset.objects.filter(asset_tag__startswith=f'AST-{year}').count() + 1:04d}"
        return f"AST-{year}-{seq}"

    def get_success_url(self):
        messages.success(self.request, f"Asset {self.object.asset_tag} created.")
        return self.object.get_absolute_url()


class AssetUpdateView(TechRequiredMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = "inventory/asset_form.html"

    def get_success_url(self):
        messages.success(self.request, "Asset updated.")
        return self.object.get_absolute_url()


class AssetDetailView(LoginRequiredMixin, DetailView):
    model = Asset
    context_object_name = "asset"
    template_name = "inventory/asset_detail.html"

    def get_queryset(self):
        return Asset.objects.select_related("category", "assigned_to_user")

    def get_context_data(self, **kwargs):
        from apps.maintenance.models import MaintenanceLog

        ctx = super().get_context_data(**kwargs)
        asset = self.object
        ctx.update(
            transactions=asset.transactions.select_related("performed_by", "assigned_to")[:20],
            maintenance_logs=MaintenanceLog.objects.filter(asset=asset)[:10],
            qr_png=qr_png_base64(asset.barcode_qr_data, box_size=5),
            barcode_svg=code128_svg(asset.barcode_qr_data),
            checkout_form=CheckOutForm(),
            checkin_form=CheckInForm(),
            statuses=AssetStatus.choices,
            can_operate=min_role("TECHNICIAN", "ADMIN")(self.request.user),
        )
        return ctx


@require_POST
def asset_check_out(request, pk):
    _guard(request, *BLOCK)
    form = CheckOutForm(request.POST)
    if not form.is_valid():
        messages.error(request, "; ".join(form.errors.get("assigned_to", ["Assignee is required."])))
        if _htmx(request):
            return _messages_html(request)
        return redirect("asset-detail", pk=pk)
    try:
        asset = check_out_asset(pk, request.user, form.cleaned_data["assigned_to"], form.cleaned_data["notes"])
        messages.success(request, f"{asset.asset_tag} checked out to {asset.assigned_to_user}.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    if _htmx(request):
        return _messages_html(request)
    return redirect("asset-detail", pk=pk)


@require_POST
def asset_check_in(request, pk):
    _guard(request, *BLOCK)
    form = CheckInForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Check-in form was invalid.")
        if _htmx(request):
            return _messages_html(request)
        return redirect("asset-detail", pk=pk)
    try:
        asset = check_in_asset(
            pk,
            request.user,
            notes=form.cleaned_data.get("notes") or "",
            new_location=form.cleaned_data.get("new_location") or None,
        )
        messages.success(request, f"{asset.asset_tag} checked in.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    if _htmx(request):
        return _messages_html(request)
    return redirect("asset-detail", pk=pk)


@require_POST
def asset_set_status(request, pk):
    _guard(request, *BLOCK)
    new_status = request.POST.get("status", "")
    if new_status not in AssetStatus.values:
        messages.error(request, "Invalid status.")
    elif new_status == AssetStatus.CHECKED_OUT:
        messages.error(request, "Use Check Out to assign the asset.")
    else:
        asset = set_asset_status(pk, request.user, new_status, notes=request.POST.get("notes", ""))
        messages.success(request, f"{asset.asset_tag} → {asset.get_status_display()}.")
    if _htmx(request):
        return _messages_html(request)
    return redirect("asset-detail", pk=pk)


# --- Label / QR / Code128 -------------------------------------------------------
@login_required
def asset_label(request, pk):
    """Printable ~2"x1" label page for Dymo/Zebra label printers."""
    asset = get_object_or_404(Asset, pk=pk)
    return render(
        request,
        "inventory/asset_label.html",
        {
            "asset": asset,
            "qr_png": qr_png_base64(asset.barcode_qr_data, box_size=6),
            "barcode_svg": code128_svg(asset.barcode_qr_data),
        },
    )


def asset_barcode_svg(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    return HttpResponse(code128_svg(asset.barcode_qr_data), content_type="image/svg+xml")


def asset_qr_png(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    raw = base64.b64decode(qr_png_base64(asset.barcode_qr_data))
    return HttpResponse(raw, content_type="image/png")


# --- Categories --------------------------------------------------------------
class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "inventory/category_list.html"
    context_object_name = "categories"


class CategoryCreateView(TechRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("category-list")

    def form_valid(self, form):
        messages.success(self.request, "Category created.")
        return super().form_valid(form)


class CategoryUpdateView(TechRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("category-list")

    def form_valid(self, form):
        messages.success(self.request, "Category updated.")
        return super().form_valid(form)


# --- Consumables ---------------------------------------------------------------
@login_required
def consumable_list(request):
    qs = Consumable.objects.select_related("category")
    term = request.GET.get("q", "").strip()
    if term:
        qs = fuzzy_search_queryset(qs, term, fields=("name", "sku", "location"))
    low_only = request.GET.get("low") == "1"
    if low_only:
        qs = qs.filter(quantity_on_hand__lte=F("minimum_threshold"))

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    ctx = {
        "page_obj": page_obj,
        "search_term": term,
        "low_only": low_only,
        "result_count": paginator.count,
    }
    if _htmx(request):
        return render(request, "inventory/partials/consumable_rows.html", ctx)
    return render(request, "inventory/consumable_list.html", ctx)


class ConsumableCreateView(TechRequiredMixin, CreateView):
    model = Consumable
    form_class = ConsumableForm
    template_name = "inventory/consumable_form.html"
    success_url = reverse_lazy("consumable-list")

    def form_valid(self, form):
        messages.success(self.request, "Consumable created.")
        return super().form_valid(form)


class ConsumableUpdateView(TechRequiredMixin, UpdateView):
    model = Consumable
    form_class = ConsumableForm
    template_name = "inventory/consumable_form.html"
    success_url = reverse_lazy("consumable-list")

    def form_valid(self, form):
        messages.success(self.request, "Consumable updated.")
        return super().form_valid(form)


@require_POST
def consumable_adjust(request, pk):
    """Increment/decrement stock by a signed delta; low-stock alert fires from
    the post_save signal in apps.alerts, never from the view."""
    _guard(request, *BLOCK)
    consumable = get_object_or_404(Consumable, pk=pk)
    try:
        delta = int(request.POST.get("delta", "0"))
    except ValueError:
        delta = 0
    if delta:
        consumable.quantity_on_hand = max(0, consumable.quantity_on_hand + delta)
        consumable.save(update_fields=["quantity_on_hand", "updated_at"])
        messages.success(request, f"{consumable.name}: {delta:+d} → {consumable.quantity_on_hand} on hand.")
    else:
        messages.error(request, "Delta must be a non-zero integer.")
    if _htmx(request):
        row = render(
            request,
            "inventory/partials/consumable_row.html",
            {"item": consumable},
        )
        return row
    return redirect("consumable-list")


# --- Web scanner (html5-qrcode) --------------------------------------------
@login_required
def scan_page(request):
    from apps.accounts.models import User

    return render(
        request,
        "inventory/scan.html",
        {"checkout_form": CheckOutForm(), "staff": User.objects.filter(is_active=True).order_by("username")},
    )


@require_POST
@login_required
def scan_lookup(request):
    """Resolve a scanned payload ('ast:AST-2026-0012' or raw asset tag)."""
    code = (request.POST.get("code") or "").strip().removeprefix("ast:")
    asset = Asset.objects.filter(barcode_qr_data__iexact=code).first() or Asset.objects.filter(
        asset_tag__iexact=code
    ).first()
    ctx = {
        "asset": asset,
        "code": code,
        "checkout_form": CheckOutForm(),
        "checkin_form": CheckInForm(),
        "can_operate": min_role("TECHNICIAN", "ADMIN")(request.user),
    }
    return render(request, "inventory/partials/scan_result.html", ctx)
