from rest_framework import routers, serializers, viewsets

from apps.accounts.permissions import IsAdminOnly, IsTechnicianOrAdmin
from config.pagination import StandardResultsSetPagination

from .models import Asset, AssetTransaction, Category, Consumable
from .search import fuzzy_search_queryset


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"


class AssetSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    assigned_to = serializers.CharField(source="assigned_to_user.username", read_only=True, default=None)

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_tag",
            "barcode_qr_data",
            "name",
            "category",
            "category_name",
            "serial_number",
            "model_number",
            "manufacturer",
            "purchase_date",
            "warranty_expiration",
            "status",
            "status_display",
            "location",
            "assigned_to",
            "custom_fields",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AssetTransactionSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    performed_by = serializers.CharField(source="performed_by.username", read_only=True, default=None)
    assigned_to = serializers.CharField(source="assigned_to.username", read_only=True, default=None)

    class Meta:
        model = AssetTransaction
        fields = ["id", "asset", "action", "action_display", "performed_by", "assigned_to", "notes", "timestamp"]


class ConsumableSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    below_threshold = serializers.SerializerMethodField()

    class Meta:
        model = Consumable
        fields = [
            "id",
            "name",
            "sku",
            "category",
            "category_name",
            "quantity_on_hand",
            "minimum_threshold",
            "unit_cost",
            "location",
            "below_threshold",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_below_threshold(self, obj):
        return obj.is_below_threshold


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsTechnicianOrAdmin()]  # read for any authenticated user
        return [IsAdminOnly()]


class AssetViewSet(viewsets.ModelViewSet):
    serializer_class = AssetSerializer
    pagination_class = StandardResultsSetPagination
    # spec 6.2: server-side pagination for lists up to 10k+ items.

    def get_queryset(self):
        qs = Asset.objects.select_related("category", "assigned_to_user")
        term = self.request.query_params.get("search")
        if term:
            qs = fuzzy_search_queryset(qs, term)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsTechnicianOrAdmin()]
        return [IsAdminOnly()]


class AssetTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Append-only audit trail: exposed read-only through the API."""

    serializer_class = AssetTransactionSerializer
    filterset_fields = ["asset", "action"]

    def get_queryset(self):
        return AssetTransaction.objects.select_related("asset", "performed_by", "assigned_to")


class ConsumableViewSet(viewsets.ModelViewSet):
    serializer_class = ConsumableSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = Consumable.objects.select_related("category")
        if self.request.query_params.get("below_threshold") in ("1", "true"):
            from django.db.models import F

            qs = qs.filter(quantity_on_hand__lte=F("minimum_threshold"))
        return qs

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsTechnicianOrAdmin()]
        return [IsAdminOnly()]


router = routers.DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("assets", AssetViewSet, basename="asset")
router.register("transactions", AssetTransactionViewSet, basename="asset-transaction")
router.register("consumables", ConsumableViewSet, basename="consumable")

urlpatterns = router.urls
