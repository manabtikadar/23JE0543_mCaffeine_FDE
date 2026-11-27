from unittest.mock import patch
from html.parser import HTMLParser

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import PurchaseOrder


class PageInputs(HTMLParser):
    """Collect successful text and hidden controls, excluding the inert row template."""
    def __init__(self, response):
        super().__init__()
        self.values = {}
        self.in_template = False
        self.feed(response.content.decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "template":
            self.in_template = True
        if tag == "input" and not self.in_template and "name" in attrs and attrs.get("type") not in {"checkbox", "file"}:
            self.values[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "template":
            self.in_template = False


class ManualDraftTests(TestCase):
    def test_sample_two_and_one_rupee_boundary(self):
        page = reverse("draft-detail", args=[self.order.pk])
        self.assertContains(self.client.get(page), "Line items not checked")
        data = {"number": "PO-2026-003", "po_date": "20.11.2026", "vendor": "XYZ Cosmetics LLP",
                "printed_total": "INR 1,42,500.00", "items-INITIAL_FORMS": "0", "items-TOTAL_FORMS": "3",
                "action": "submit"}
        for index, (sku, description, qty, price, amount) in enumerate([
            ("MC-001", "Body Wash 200ml", 500, "INR 120.00", "60,000.00"),
            ("MC-014", "Coffee Face Scrub 100g", 300, "Rs. 95.00", "28,500.00"),
            ("HY-203", "Sunscreen SPF50 50ml", 200, "₹180.00", "36,000.00"),
        ]):
            for key, value in dict(sku=sku, description=description, quantity=qty, unit_price=price, line_total=amount).items():
                data[f"items-{index}-{key}"] = value
        response = self.client.post(page, data)
        self.assertContains(response, "Difference ₹18,000.00")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DRAFT")
        self.assertFalse(self.order.history.exists())
        data.update({"items-0-line_total": "60001.01", "printed_total": "124502.02"})
        response = self.client.post(page, data)
        self.assertIn("line_total", response.context["items"][0].errors)
        self.assertIn("printed_total", response.context["form"].errors)
        data.update({"items-0-line_total": "60001.00", "printed_total": "124502.00"})
        self.assertRedirects(self.client.post(page, data), page)
        self.order.refresh_from_db()
        self.assertEqual(self.order.printed_total, 12450200)
        self.assertEqual(self.order.items.get(sku="MC-001").unit_price, 12000)
        self.assertEqual(self.order.po_date.isoformat(), "2026-11-20")
        self.assertContains(self.client.get(page), "20-11-2026")

    def test_edit_page_save_reopen_and_submit(self):
        page = reverse("draft-detail", args=[self.order.pk])
        response = self.client.get(page)
        data = PageInputs(response).values
        fields = {"number": self.order.number, "vendor": "ABC", "po_date": "15-11-2026",
                  "printed_total": "60.00", "items-0-sku": "MC-001", "items-0-description": "Body wash",
                  "items-0-quantity": "2", "items-0-unit_price": "30.00", "items-0-line_total": "60.00"}
        self.assertTrue(fields.keys() <= data.keys())
        self.assertEqual(data["number"], self.order.number)
        data.update(fields)
        invalid = self.client.post(page, {**data, "number": ""})
        self.assertContains(invalid, "This field is required")
        self.assertEqual(PageInputs(invalid).values["vendor"], "ABC")
        self.assertFalse(self.order.items.exists())
        self.assertRedirects(self.client.post(page, data), page)
        reopened = self.client.get(page)
        saved = PageInputs(reopened).values
        for name, value in fields.items():
            self.assertEqual(saved[name], value)
        self.assertContains(reopened, 'value="submit"')
        rejected = self.client.post(page, {**saved, "action": "submit", "printed_total": "99.00"})
        self.assertContains(rejected, "Printed total must match")
        self.assertEqual(PageInputs(rejected).values["printed_total"], "99.00")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.DRAFT)
        self.assertRedirects(self.client.post(page, {**saved, "action": "submit"}), page)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PurchaseOrder.Status.SUBMITTED)
        approver = User.objects.create_user("approver1")
        Group.objects.create(name="Approver").user_set.add(approver)
        self.client.force_login(approver)
        queue = self.client.get(reverse("approval-queue")).json()["orders"]
        self.assertEqual([row["id"] for row in queue], [self.order.pk])

    def setUp(self):
        self.owner = User.objects.create_user("owner")
        self.other = User.objects.create_user("other")
        group = Group.objects.create(name="Creator")
        group.user_set.add(self.owner, self.other)
        self.order = PurchaseOrder.objects.create(number="PO-1", creator=self.owner)
        self.client.force_login(self.owner)

    def test_normalized_uniqueness_applies_to_database_writes(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseOrder.objects.create(number=" po-1 ", creator=self.other)

    @patch("orders.storage.check_bucket")
    @patch("orders.storage.storage_request")
    def test_save_reopen_and_private_access(self, request, bucket):
        pdf = b"%PDF-1.4\noriginal"
        page = reverse("draft-detail", args=[self.order.pk])
        original = reverse("original", args=[self.order.pk])
        response = self.client.post(page, {
            "number": "PO-1", "vendor": "ABC", "po_date": "2026-11-15", "printed_total": "60.00",
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0", "items-0-sku": "MC-001",
            "items-0-description": "Body wash", "items-0-quantity": "2", "items-0-unit_price": "30",
            "items-0-line_total": "60", "pdf": SimpleUploadedFile("po.pdf", pdf),
        })
        self.assertRedirects(response, page)
        self.order.refresh_from_db()
        self.assertEqual(self.order.items.get().sku, "MC-001")
        self.assertEqual(self.order.vendor, "ABC")
        request.assert_called_once_with("object/po-originals/" + self.order.pdf_key, "POST", pdf, "application/pdf")
        self.assertContains(self.client.get(page), "Open original PDF")
        request.return_value = pdf
        self.assertEqual(self.client.get(original).content, pdf)
        self.client.force_login(self.other)
        request.reset_mock()
        self.assertEqual(self.client.get(page).status_code, 404)
        self.assertEqual(self.client.get(original).status_code, 404)
        request.assert_not_called()
