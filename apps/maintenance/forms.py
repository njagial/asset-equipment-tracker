from django import forms

from .models import MaintenanceLog, MaintenanceStatus, MaintenanceType


class MaintenanceLogForm(forms.ModelForm):
    class Meta:
        model = MaintenanceLog
        fields = [
            "asset",
            "maintenance_type",
            "title",
            "description",
            "vendor",
            "cost",
            "scheduled_date",
            "status",
            "is_recurring",
            "recurrence_days",
        ]
        widgets = {
            "scheduled_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "vendor": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].widget.attrs.setdefault("class", "form-select")
        self.fields["maintenance_type"].widget.attrs.setdefault("class", "form-select")


STATUS_CHOICES = MaintenanceStatus.choices
TYPE_CHOICES = MaintenanceType.choices
