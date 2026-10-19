"""Context processor: badged counts for the navbar."""
from django.db.models import F, Q

from .models import Consumable


def nav_badges(request):
    if not request.user.is_authenticated:
        return {}
    low_stock = Consumable.objects.filter(Q(quantity_on_hand__lte=F("minimum_threshold"))).count()
    return {"low_stock_count": low_stock}
