from uuid import uuid4

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from . import storage
from .access import CREATOR, roles_for, visible_orders
from .models import LineItem, PurchaseOrder


class HeaderForm(forms.ModelForm):
    pdf = forms.FileField(required=False, label="Original PDF (up to 5 MB)")

    class Meta:
        model = PurchaseOrder
        fields = ["number", "po_date", "vendor", "printed_total"]
        widgets = {"po_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

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


Items = inlineformset_factory(PurchaseOrder, LineItem, fields=["sku", "description", "quantity", "unit_price", "line_total"], extra=1, can_delete=True)


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
            editable = CREATOR in roles and order.creator_id == request.user.pk and order.status == "DRAFT"
            if request.method == "POST" and not editable:
                return HttpResponse("Permission denied.", status=403)
            data = request.POST if request.method == "POST" else None
            form = HeaderForm(data, request.FILES, instance=order)
            items = Items(data, instance=order)
            if data is not None and form.is_valid() and items.is_valid():
                file = form.cleaned_data["pdf"]
                if file:
                    storage.check_bucket()
                    key = f"{order.pk}/{uuid4().hex}.pdf"
                    storage.storage_request("object/po-originals/" + key, "POST", file.read(), "application/pdf")
                    saved_key = order.pdf_key = key
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
    return render(request, "orders/detail.html", {"order": order, "form": form, "items": items, "editable": editable})


@login_required
@require_safe
@never_cache
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
    response["Content-Security-Policy"] = "sandbox"
    return response
