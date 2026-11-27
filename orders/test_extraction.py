from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .extraction import read_header
from .models import PurchaseOrder
from .test_drafts import PageInputs


BRIEF = Path(__file__).resolve().parent.parent / "brief"


class ExtractionTests(TestCase):
    @skipUnless((BRIEF / "sample_1_digital.pdf").exists(), "Requires the assignment PDFs in brief/")
    @patch("orders.views.check_bucket")
    @patch("orders.views.storage_request")
    def test_read_stored_pdf_without_reuploading_or_overwriting(self, storage_request, check_bucket):
        owner = User.objects.create_user("prior-creator")
        owner.groups.add(Group.objects.create(name="Creator"))
        self.client.force_login(owner)
        order = PurchaseOrder.objects.create(creator=owner, number="PO-2026-001", pdf_key="uploads/original.pdf")
        storage_request.return_value = (BRIEF / "sample_1_digital.pdf").read_bytes()
        path = reverse("read-original-items", args=[order.pk])
        self.assertRedirects(self.client.post(path), reverse("draft-detail", args=[order.pk]))
        self.assertEqual(self.client.post(path).status_code, 409)
        self.assertEqual(order.items.count(), 5)
        storage_request.assert_called_once_with("object/authenticated/po-originals/uploads/original.pdf")

    def test_labelled_values_and_noisy_text(self):
        header = "Order No.: PO-42\nOrder Date: 15/11/2026\nSupplier: Green Leaf\nGrand Total: Rs. 124500"
        fields = read_header(header)
        self.assertEqual(fields["printed_total"], 12450000)
        self.assertEqual(fields["po_date"].isoformat(), "2026-11-15")
        self.assertEqual(read_header("†£÷" * 600), {})

    @skipUnless((BRIEF / "sample_4_garbled.pdf").exists(), "Requires the assignment PDFs in brief/")
    @patch("orders.storage.check_bucket")
    @patch("orders.storage.storage_request")
    def test_workspace_upload_with_supplied_pdfs(self, storage_request, check_bucket):
        user = User.objects.create_user("sample-reviewer")
        user.groups.add(Group.objects.create(name="Creator"))
        self.client.force_login(user)

        def upload(filename):
            pdf = SimpleUploadedFile(filename, (BRIEF / filename).read_bytes(), "application/pdf")
            return self.client.post("/", {"action": "upload", "pdf": pdf}, follow=True)

        for filename, number, vendor, date, total in [
            ("sample_1_digital.pdf", "PO-2026-001", "ABC Industries", "2026-11-15", 25420000),
            ("sample_2_mismatch.pdf", "PO-2026-003", "XYZ Cosmetics LLP", "2026-11-20", 14250000),
        ]:
            response = upload(filename)
            self.assertContains(response, "PDF text layer")
            order = PurchaseOrder.objects.get(number=number)
            self.assertEqual((order.vendor, order.po_date.isoformat(), order.printed_total), (vendor, date, total))
            rows = list(order.items.order_by("pk"))
            if number == "PO-2026-001":
                self.assertNotContains(response, 'id="total-warning"')
                self.assertEqual(len(rows), 5)
                self.assertEqual([row.sku for row in rows], ["MC-001", "MC-014", "HY-203", "MC-027", "HY-118"])
                self.assertEqual(rows[3].description, "Coffee Body Scrub with Arabica Extract and Walnut Shell 250g")
                self.assertEqual((rows[3].quantity, rows[3].unit_price, rows[3].line_total), (150, 21000, 3150000))
                self.assertEqual(sum(row.line_total for row in rows), 25420000)
                rendered = PageInputs(response).values
                self.assertEqual(rendered["items-INITIAL_FORMS"], "5")
                self.assertEqual(rendered["items-3-description"], rows[3].description)
                rendered.update({"items-0-description": "Reviewed body wash", "action": "submit"})
                self.client.post(reverse("draft-detail", args=[order.pk]), rendered)
                order.refresh_from_db()
                self.assertEqual(order.status, "SUBMITTED")
                self.assertEqual(order.items.get(sku="MC-001").description, "Reviewed body wash")
            else:
                self.assertContains(response, "Difference ₹18,000.00")
                self.assertContains(self.client.get(reverse("draft-detail", args=[order.pk])), "Difference ₹18,000.00")
                self.assertEqual(len(rows), 3)
                self.assertEqual(sum(row.line_total for row in rows), 12450000)
                invalid = self.client.post(reverse("draft-detail", args=[order.pk]),
                                           {**PageInputs(response).values, "action": "submit"})
                self.assertContains(invalid, "Difference ₹18,000.00")
                order.refresh_from_db()
                self.assertEqual(order.status, "DRAFT")
        other = User.objects.create_user("other-creator")
        other.groups.add(Group.objects.get(name="Creator"))
        self.client.force_login(other)
        duplicate = upload("sample_3_resent.pdf")
        self.assertContains(duplicate, "PO number already exists.")
        self.assertNotContains(duplicate, "sample-reviewer")
        self.assertFalse(PurchaseOrder.objects.filter(creator=other).exists())
        self.assertEqual(storage_request.call_count, 2)
        response = upload("sample_4_garbled.pdf")
        self.assertContains(response, "This PDF can’t be read automatically")
        order = response.context["order"]
        self.assertEqual((order.number, order.vendor, order.po_date, order.printed_total), (None, "", None, None))
        self.assertEqual(order.extraction_method, "unreadable")
        self.assertFalse(order.items.exists())
        self.assertContains(response, 'title="Original purchase order PDF"')
        original = (BRIEF / "sample_4_garbled.pdf").read_bytes()
        storage_request.assert_called_with("object/po-originals/" + order.pdf_key, "POST", original, "application/pdf")
        storage_request.return_value = original
        preview = self.client.get(reverse("original", args=[order.pk]))
        self.assertEqual(preview.content, original)
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
