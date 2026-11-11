from django import forms

from .models import Order


class CheckoutForm(forms.ModelForm):

    class Meta:
        model = Order

        fields = (
            "customer_name",
            "phone_number",
            "delivery_address",
            "notes",
        )

        widgets = {
            "customer_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your full name",
                }
            ),
            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "01XXXXXXXXX",
                }
            ),
            "delivery_address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "House, road, area, district",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional delivery instructions",
                }
            ),
        }