from django.conf import settings
from django.db import models
from django.db.models.functions import Trim, Upper


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"

    number = models.CharField(max_length=64, unique=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=Status, default=Status.DRAFT)
    vendor = models.CharField(max_length=200, blank=True)
    po_date = models.DateField(null=True, blank=True)
    printed_total = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    pdf_key = models.CharField(max_length=160, blank=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(Upper(Trim("number")), name="po_normalized_number_unique")]


class LineItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, related_name="items", on_delete=models.CASCADE)
    sku = models.CharField(max_length=64)
    description = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=16, decimal_places=2)
