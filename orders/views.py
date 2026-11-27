import json

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from .access import APPROVER, CREATOR, roles_for, visible_orders
from .models import HistoryEntry, PurchaseOrder


class DraftForm(forms.Form):
    number = forms.CharField(label="PO number", max_length=64)

    def clean_number(self):
        number = self.cleaned_data["number"].upper()
        if len(number) > 64:
            raise forms.ValidationError("Use at most 64 characters for the PO number.")
        return number

    def create_for(self, user):
        if self.is_valid():
            order, created = PurchaseOrder.objects.get_or_create(
                number=self.cleaned_data["number"], defaults={"creator": user}
            )
            if created:
                return order
            self.add_error("number", "PO number already exists.")
        return None


def forbidden():
    return JsonResponse({"detail": "Permission denied."}, status=403)


@login_required
@require_http_methods(["GET", "POST"])
def workspace(request):
    roles = roles_for(request.user)
    if not roles or (request.method == "POST" and CREATOR not in roles):
        return forbidden()
    form = DraftForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.create_for(request.user):
        return redirect("workspace")
    return render(request, "orders/workspace.html", {
        "roles": sorted(roles),
        "can_create": CREATOR in roles,
        "can_review": APPROVER in roles,
        "orders": visible_orders(request.user, roles),
        "form": form,
    })


ORDER_FIELDS = ("id", "number", "status")


@require_http_methods(["GET", "HEAD", "POST"])
def order_list(request):
    roles = roles_for(request.user)
    if not roles or (request.method == "POST" and CREATOR not in roles):
        return forbidden()
    if request.method == "POST":
        data = request.POST
        if request.content_type == "application/json":
            try:
                data = json.loads(request.body)
            except (ValueError, UnicodeDecodeError):
                data = None
            if not isinstance(data, dict):
                return JsonResponse({"detail": "Expected a JSON object."}, status=400)
        form = DraftForm(data)
        order = form.create_for(request.user)
        if order is None:
            return JsonResponse({"errors": form.errors}, status=400)
        return JsonResponse({"id": order.pk, "number": order.number, "status": order.status}, status=201)
    orders = visible_orders(request.user, roles).values(*ORDER_FIELDS)
    return JsonResponse({"orders": list(orders)})


@require_safe
def order_detail(request, pk):
    roles = roles_for(request.user)
    if not roles:
        return forbidden()
    order = visible_orders(request.user, roles).filter(pk=pk).values(*ORDER_FIELDS).first()
    if order is None:
        return JsonResponse({"detail": "PO not found."}, status=404)
    return JsonResponse(order)


@require_safe
def approval_queue(request):
    if APPROVER not in roles_for(request.user):
        return forbidden()
    orders = PurchaseOrder.objects.filter(status=PurchaseOrder.Status.SUBMITTED).order_by("pk")
    if request.GET.get("view") == "page":
        return render(request, "orders/queue.html", {"orders": orders})
    return JsonResponse({"orders": list(orders.values(*ORDER_FIELDS))})


@require_POST
@transaction.atomic
def decide(request, pk, action):
    if APPROVER not in roles_for(request.user):
        return forbidden()
    order = PurchaseOrder.objects.select_for_update().filter(pk=pk).first()
    if order is None or (order.status == PurchaseOrder.Status.DRAFT and order.creator_id != request.user.pk):
        return JsonResponse({"detail": "PO not found."}, status=404)
    if order.creator_id == request.user.pk:
        return forbidden()
    if order.status != PurchaseOrder.Status.SUBMITTED:
        return JsonResponse({"detail": "Only submitted orders can be decided."}, status=409)
    data = request.POST
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            return JsonResponse({"detail": "Expected a JSON object."}, status=400)
    remark = data.get("reason", data.get("remark", ""))
    if not isinstance(remark, str) or (action == HistoryEntry.Action.REJECT and not remark.strip()):
        return JsonResponse({"detail": "Enter a reason for rejection."}, status=400)
    order.status = PurchaseOrder.Status.APPROVED if action == HistoryEntry.Action.APPROVE else PurchaseOrder.Status.REJECTED
    order.save(update_fields=["status"])
    HistoryEntry.objects.create(order=order, actor=request.user, action=action, remark=remark.strip())
    if request.POST.get("from_detail") == "1":
        return redirect("workspace")
    return JsonResponse({"id": order.pk, "status": order.status})
