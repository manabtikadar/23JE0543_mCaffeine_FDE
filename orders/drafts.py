from uuid import uuid4
from decimal import Decimal

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods, require_safe

from . import storage
from .access import APPROVER, CREATOR, roles_for, visible_orders
from .models import HistoryEntry, LineItem, PurchaseOrder
from .money import MoneyInput, RupeeModelForm, rupees


class HeaderForm(RupeeModelForm):
    po_date = forms.DateField(required=False, label="PO date (DD-MM-YYYY)",
        input_formats=["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y"],
        widget=forms.DateInput(format="%d-%m-%Y"))
    printed_total = MoneyInput(required=False, decimal_places=2, max_digits=16)
    pdf = forms.FileField(required=False, label="Original PDF (up to 5 MB)")

    class Meta:
        model = PurchaseOrder
        fields = ["number", "po_date", "vendor", "printed_total"]

    def clean_number(self):
        value = self.cleaned_data["number"].strip().upper()
        if len(value) > 64:
            raise forms.ValidationError("Use at most 64 characters.")
        return value

    def clean_pdf(self):
        file = self.cleaned_data["pdf"]
        if file:
            if self.instance.pdf_key:
                raise forms.ValidationError("This order already has its original PDF.")
            if file.size > 5 * 1024 * 1024 or file.read(5) != b"%PDF-":
                raise forms.ValidationError("Choose a PDF up to 5 MB.")
            file.seek(0)
        return file


class LineForm(RupeeModelForm):
    quantity = forms.IntegerField(min_value=1)
    unit_price = MoneyInput(min_value=Decimal("0.01"), decimal_places=2, max_digits=14)
    line_total = MoneyInput(decimal_places=2, max_digits=16)

    class Meta:
        model = LineItem
        fields = ["sku", "description", "quantity", "unit_price", "line_total"]


Items = inlineformset_factory(PurchaseOrder, LineItem, form=LineForm, fields=["sku", "description", "quantity", "unit_price", "line_total"], extra=1, can_delete=True)


def total_warning(printed, line_sum):
    if printed is None or line_sum is None or abs(printed - line_sum) <= 100:
        return ""
    return (f"Printed total must match the line items within ₹1. Printed total ₹{rupees(printed):,.2f}. "
            f"Lines total ₹{rupees(line_sum):,.2f}. Difference ₹{rupees(abs(printed - line_sum)):,.2f}.")


def validate_line_amounts(items):
    for row in items:
        values = row.cleaned_data
        if values.get("DELETE") or not {"quantity", "unit_price", "line_total"} <= values.keys():
            continue
        expected = values["quantity"] * values["unit_price"]
        if abs(expected - values["line_total"]) > 100:
            row.add_error("line_total", f"Quantity × unit price gives ₹{rupees(expected):,.2f}. Check the line total (₹1 tolerance).")


def validate_submission(form, items):
    existing = set(items.get_queryset().values_list("pk", flat=True))
    posted = [row.instance.pk for row in items.initial_forms]
    if len(posted) != len(existing) or set(posted) != existing:
        form.add_error(None, "The line items changed. Reload the draft before submitting.")
        return
    amounts = [row.cleaned_data["line_total"] for row in items if row.cleaned_data and not row.cleaned_data.get("DELETE")]
    warning = total_warning(form.cleaned_data.get("printed_total"), sum(amounts) if amounts else None)
    if warning:
        form.add_error("printed_total", warning)


@login_required
@require_http_methods(["GET", "POST"])
def detail(request, pk):
    roles = roles_for(request.user)
    saved_key = None
    try:
        with transaction.atomic():
            orders = visible_orders(request.user, roles)
            if request.method == "POST":
                orders = orders.select_for_update()
            order = get_object_or_404(orders, pk=pk)
            editable = CREATOR in roles and order.creator_id == request.user.pk and order.status in (
                PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.REJECTED
            )
            if request.method == "POST" and not editable:
                return HttpResponse("Permission denied.", status=403)
            data = request.POST if request.method == "POST" else None
            form = HeaderForm(data, request.FILES if data is not None else None, instance=order)
            items = Items(data, instance=order)
            submitting = request.POST.get("action") == "submit"
            if submitting:
                for name in ("po_date", "vendor", "printed_total"):
                    form.fields[name].required = True
            if data is not None:
                rows_valid = items.is_valid()
                if submitting and rows_valid and form.is_valid():
                    validate_submission(form, items)
                validate_line_amounts(items)
            if data is not None and form.is_valid() and items.is_valid():
                file = form.cleaned_data["pdf"]
                if file:
                    storage.check_bucket()
                    key = f"{order.pk}/{uuid4().hex}.pdf"
                    storage.storage_request("object/po-originals/" + key, "POST", file.read(), "application/pdf")
                    saved_key = order.pdf_key = key
                if submitting:
                    action = HistoryEntry.Action.RESUBMIT if order.status == PurchaseOrder.Status.REJECTED else HistoryEntry.Action.SUBMIT
                    HistoryEntry.objects.create(order=order, actor=request.user, action=action)
                    order.status = PurchaseOrder.Status.SUBMITTED
                form.save()
                items.save()
                return redirect("draft-detail", pk=pk)
    except storage.StorageUnavailable as exc:
        form.add_error("pdf", str(exc))
    except IntegrityError as exc:
        if saved_key:
            storage.storage_request("object/po-originals/" + saved_key, "DELETE")
        if getattr(exc.__cause__, "sqlstate", None) != "23505":
            raise
        form.add_error("number", "PO number already exists.")
    line_sum = order.items.aggregate(total=Sum("line_total"))["total"]
    has_lines = line_sum is not None
    warning = total_warning(order.printed_total, line_sum) if not form.is_bound else ""
    if warning and editable:
        form.fields["printed_total"].widget.attrs.update({"aria-invalid": "true", "aria-describedby": "total-warning"})
    if items.is_bound:
        has_lines = any(row.has_changed() or row.instance.pk for row in items
                        if not row.cleaned_data.get("DELETE")) if items.is_valid() else True
    history = list(order.history.select_related("actor"))
    decision = next((entry for entry in reversed(history)
                     if entry.action in (HistoryEntry.Action.APPROVE, HistoryEntry.Action.REJECT)), None)
    return render(request, "orders/detail.html", {
        "order": order, "form": form, "items": items, "editable": editable,
        "has_lines": has_lines,
        "total_warning": warning,
        "can_decide": APPROVER in roles and request.user.pk != order.creator_id and order.status == PurchaseOrder.Status.SUBMITTED,
        "history": history, "decision": decision,
    })


@login_required
@require_safe
@never_cache
@xframe_options_sameorigin
def original(request, pk):
    order = get_object_or_404(visible_orders(request.user, roles_for(request.user)), pk=pk)
    if not order.pdf_key:
        raise Http404
    try:
        storage.check_bucket()
        pdf = storage.storage_request("object/authenticated/po-originals/" + order.pdf_key)
    except storage.StorageUnavailable as exc:
        return HttpResponse(str(exc), status=503)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="purchase-order.pdf"'
    response["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def delete_draft(request, pk):
    if CREATOR not in roles_for(request.user):
        return HttpResponse("Permission denied.", status=403)
    context = {"pk": pk}
    try:
        with transaction.atomic():
            orders = PurchaseOrder.objects.filter(creator=request.user)
            if request.method == "POST":
                orders = orders.select_for_update()
            order = get_object_or_404(orders, pk=pk)
            if order.status != PurchaseOrder.Status.DRAFT or order.history.exists():
                return HttpResponse("Only an unsubmitted draft can be deleted.", status=409)
            context["number"] = order.number
            if request.method == "POST":
                key = order.pdf_key
                order.delete()
                if key:
                    storage.delete_original(key)
                return redirect("workspace")
    except storage.StorageUnavailable:
        context["error"] = "PDF storage could not confirm deletion. The draft was retained. Please retry."
        return render(request, "orders/delete.html", context, status=503)
    return render(request, "orders/delete.html", context)
