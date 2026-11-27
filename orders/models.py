from django.conf import settings
from django.db import models
from django.db.models.functions import Trim, Upper


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        REJECTED = "REJECTED", "Rejected"
        APPROVED = "APPROVED", "Approved"

    class Extraction(models.TextChoices):
        MANUAL = "manual", "Manual entry"
        TEXT = "text_layer", "PDF text layer"
        UNREADABLE = "unreadable", "Manual entry (unreadable text layer)"

    number = models.CharField(max_length=64, unique=True, null=True)
    extraction_method = models.CharField(max_length=16, choices=Extraction, default=Extraction.MANUAL)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=Status, default=Status.DRAFT)
    vendor = models.CharField(max_length=200, blank=True)
    po_date = models.DateField(null=True, blank=True)
    printed_total = models.BigIntegerField(db_column="printed_total_paise", null=True, blank=True)
    pdf_key = models.CharField(max_length=160, blank=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(Upper(Trim("number")), name="po_normalized_number_unique")]


class LineItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, related_name="items", on_delete=models.CASCADE)
    sku = models.CharField(max_length=64)
    description = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField()
    unit_price = models.BigIntegerField(db_column="unit_price_paise")
    line_total = models.BigIntegerField(db_column="line_total_paise")


class HistoryEntry(models.Model):
    class Action(models.TextChoices):
        SUBMIT = "SUBMIT", "Submitted"
        RESUBMIT = "RESUBMIT", "Resubmitted"
        APPROVE = "APPROVE", "Approved"
        REJECT = "REJECT", "Rejected"

    order = models.ForeignKey(PurchaseOrder, related_name="history", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=8, choices=Action)
    recorded_at = models.DateTimeField(auto_now_add=True)
    remark = models.TextField(blank=True)

    class Meta:
        ordering = ["pk"]
