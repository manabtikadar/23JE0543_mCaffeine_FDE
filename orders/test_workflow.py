from django.contrib.auth.models import Group, User
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import PurchaseOrder


class WorkflowTests(TestCase):
    def test_dual_role_owner_and_full_decision_history(self):
        lead = User.objects.create_user("lead1")
        finance = User.objects.create_user("approver1")
        creator = Group.objects.create(name="Creator")
        approver = Group.objects.create(name="Approver")
        lead.groups.add(creator, approver)
        finance.groups.add(approver)
        order = PurchaseOrder.objects.create(number="PO-LEAD", creator=lead)
        page = reverse("draft-detail", args=[order.pk])
        approve = reverse("approve", args=[order.pk])
        reject = reverse("reject", args=[order.pk])
        data = {
            "number": order.number, "vendor": "ABC", "po_date": "2026-11-15", "printed_total": "20",
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0", "items-0-sku": "ABC-1",
            "items-0-description": "Wash", "items-0-quantity": "2", "items-0-unit_price": "10",
            "items-0-line_total": "20", "action": "submit",
        }
        self.client.force_login(lead)
        self.assertRedirects(self.client.post(page, data), page)
        self.assertEqual(self.client.post(approve).status_code, 403)
        self.assertEqual(self.client.post(reject, {"reason": "Wrong"}).status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, "SUBMITTED")
        self.assertEqual(list(order.history.values_list("action", flat=True)), ["SUBMIT"])
        self.assertEqual(self.client.post(page, data).status_code, 403)
        self.client.force_login(finance)
        self.assertEqual(self.client.post(reject, {"reason": "  "}).status_code, 400)
        self.assertEqual(self.client.post(reject, {"reason": "Correct vendor"}).status_code, 200)
        self.assertEqual(self.client.post(page, data).status_code, 404)
        self.client.force_login(lead)
        self.assertContains(self.client.get(page), "Correct vendor")
        data.update({"vendor": "Corrected", "items-INITIAL_FORMS": "1", "items-0-id": order.items.get().pk})
        self.assertRedirects(self.client.post(page, data), page)
        self.client.force_login(finance)
        self.assertEqual(self.client.get(reverse("approval-queue")).json()["orders"][0]["id"], order.pk)
        self.assertEqual(self.client.post(approve, {"remark": "Checked"}).status_code, 200)
        self.assertEqual(self.client.post(approve).status_code, 409)
        self.assertEqual(self.client.post(reject, {"reason": "Late"}).status_code, 409)
        order.refresh_from_db()
        self.assertEqual((order.status, order.vendor), ("APPROVED", "Corrected"))
        self.client.force_login(lead)
        self.assertEqual(self.client.post(page, data).status_code, 403)
        self.assertEqual(list(order.history.values_list("action", "actor__username", "remark")), [
            ("SUBMIT", "lead1", ""), ("REJECT", "approver1", "Correct vendor"),
            ("RESUBMIT", "lead1", ""), ("APPROVE", "approver1", "Checked"),
        ])
        self.assertFalse(order.history.filter(recorded_at=None).exists())
        with self.assertRaises(DatabaseError), transaction.atomic():
            order.history.update(remark="Edited")
        with self.assertRaises(DatabaseError), transaction.atomic():
            order.history.all().delete()
