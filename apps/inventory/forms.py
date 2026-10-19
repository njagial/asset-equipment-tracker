import json

from django import forms

from apps.accounts.models import User

from .models import Asset, AssetStatus, Category, Consumable


class JSONTextareaWidget(forms.Textarea):
    def prepare_value(self, value):
        if isinstance(value, dict):
            return json.dumps(value, indent=2)
        return value


class AssetForm(forms.ModelForm):
    custom_fields = forms.CharField(
        required=False,
        widget=JSONTextareaWidget(attrs={"rows": 5, "class": "form-control font-monospace"}),
        help_text="Optional flexible metadata as JSON, e.g. {\"voltage\": \"220V\", \"bulb_hours\": 1200}",
    )

    class Meta:
        model = Asset
        fields = [
            "name",
            "category",
            "asset_tag",
            "serial_number",
            "model_number",
            "manufacturer",
            "purchase_date",
            "warranty_expiration",
            "location",
            "status",
            "custom_fields",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")

    def clean_custom_fields(self):
        raw = self.cleaned_data.get("custom_fields") or ""
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f'custom_fields must be valid JSON: "{exc}"') from exc
        if not isinstance(data, dict):
            raise forms.ValidationError("custom_fields must be a JSON object.")
        return data


class ConsumableForm(forms.ModelForm):
    class Meta:
        model = Consumable
        fields = ["name", "sku", "category", "quantity_on_hand", "minimum_threshold", "unit_cost", "location"]
        widgets = {"location": forms.TextInput()}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]


class CheckOutForm(forms.Form):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        label="Assignee",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}))

    class Media:
        pass


class CheckInForm(forms.Form):
    new_location = forms.CharField(
        max_length=255,
        required=False,
        label="Return location (optional)",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}))


ASSET_STATUS_CHOICES = AssetStatus.choices
