import re
from io import BytesIO
from uuid import uuid4

import pdfplumber
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from pdfplumber.utils.exceptions import MalformedPDFException, PdfminerException

from . import storage
from .drafts import HeaderForm
from .models import PurchaseOrder


def read_header(text):
    def match(pattern):
        found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return found.group(1).strip() if found else ""

    number = match(r"^(?:PO Number|P\.O\. #|(?:Purchase )?Order No\.?)\s*:?[^\S\n]*([A-Z0-9][A-Z0-9/_-]{0,63})(?=\s|$)")
    date = match(r"(?:PO Date|Order Date)\s*:[ \t]*([^\n]+)$")
    vendor = match(r"^(?:Vendor|Supplier)[ \t]*:[ \t]*(.+?)(?:[ \t]+Delivery[ \t]*:.*)?$")
    total = match(r"^(?:PO Total|Grand Total)[ \t]*:?[ \t]*(.+)$")
    fields = {}
    if number:
        fields["number"] = number.upper()
    if vendor and len(vendor) <= 200 and any(char.isalpha() for char in vendor):
        fields["vendor"] = vendor
    for name, value in (("po_date", date), ("printed_total", total)):
        if value:
            try:
                fields[name] = HeaderForm.base_fields[name].clean(value)
            except ValidationError:
                pass  # Leave an ambiguous date or amount for manual review.
    # Demand corroborating labelled values. A nonempty hidden layer can be nonsense.
    return fields if len(fields) >= 2 else {}


def upload_draft(user, upload):
    if not upload or upload.size > 5 * 1024 * 1024:
        raise ValidationError("Choose one PDF up to 5 MB.")
    data = upload.read()
    if not data.startswith(b"%PDF-"):
        raise ValidationError("Choose a valid PDF.")
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except (PdfminerException, MalformedPDFException, ValueError) as exc:
        raise ValidationError("This PDF could not be opened. Choose a readable, unlocked PDF.") from exc
    fields = read_header(text)
    method = PurchaseOrder.Extraction.TEXT if fields else PurchaseOrder.Extraction.UNREADABLE
    key = f"uploads/{uuid4().hex}.pdf"
    uploaded = False
    try:
        with transaction.atomic():
            order = PurchaseOrder.objects.create(creator=user, pdf_key=key, extraction_method=method, **fields)
            storage.check_bucket()
            storage.storage_request("object/po-originals/" + key, "POST", data, "application/pdf")
            uploaded = True
        uploaded = False  # The committed draft now owns the object.
        return order
    except IntegrityError as exc:
        if getattr(exc.__cause__, "sqlstate", None) == "23505":
            raise ValidationError("PO number already exists.") from exc
        raise
    finally:
        # A commit failure after the object was written must not leave an orphan.
        if uploaded:
            storage.storage_request("object/po-originals/" + key, "DELETE")
