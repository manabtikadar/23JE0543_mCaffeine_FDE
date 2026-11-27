from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .extraction import read_header
from .models import PurchaseOrder


BRIEF = Path(__file__).resolve().parent.parent / "brief"


class ExtractionTests(TestCase):
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
            self.assertFalse(order.items.exists())
        self.assertContains(upload("sample_3_resent.pdf"), "PO number already exists.")
        self.assertEqual(storage_request.call_count, 2)
        response = upload("sample_4_garbled.pdf")
        self.assertContains(response, "This PDF can’t be read automatically")
        order = response.context["order"]
        self.assertEqual((order.number, order.vendor, order.po_date, order.printed_total), (None, "", None, None))
        self.assertEqual(order.extraction_method, "unreadable")
        self.assertContains(response, 'title="Original purchase order PDF"')
        original = (BRIEF / "sample_4_garbled.pdf").read_bytes()
        storage_request.assert_called_with("object/po-originals/" + order.pdf_key, "POST", original, "application/pdf")
        storage_request.return_value = original
        preview = self.client.get(reverse("original", args=[order.pk]))
        self.assertEqual(preview.content, original)
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
