import re
from decimal import Decimal

from django import forms


def rupees(paise):
    return None if paise is None else Decimal(paise).scaleb(-2)


class MoneyInput(forms.DecimalField):
    """Read rupees from the form and give the model integer paise."""
    widget = forms.TextInput

    def to_python(self, value):
        if isinstance(value, str) and value.strip():
            value = re.sub(r"^(?:₹|Rs\.?|INR)\s*", "", value.strip(), flags=re.I)
            if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.\d{1,2})?", value):
                raise forms.ValidationError("Enter a rupee amount with up to two decimal places.")
            value = value.replace(",", "")
        return super().to_python(value)

    def clean(self, value):
        amount = super().clean(value)
        return None if amount is None else int(amount * 100)


class RupeeModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field, MoneyInput):
                self.initial[name] = rupees(self.initial.get(name))
