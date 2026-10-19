from django.urls import include, path
from rest_framework import routers, serializers, viewsets

from apps.accounts.permissions import IsAdminOnly, IsTechnicianOrAdmin

from .models import MaintenanceLog


class MaintenanceLogSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    type_display = serializers.CharField(source="get_maintenance_type_display", read_only=True)
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    performed_by = serializers.CharField(source="performed_by.username", read_only=True, default=None)

    class Meta:
        model = MaintenanceLog
        fields = [
            "id",
            "asset",
            "asset_tag",
            "maintenance_type",
            "type_display",
            "title",
            "description",
            "performed_by",
            "vendor",
            "cost",
            "scheduled_date",
            "completed_date",
            "status",
            "status_display",
            "is_recurring",
            "recurrence_days",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        completed = attrs.get("completed_date")
        scheduled = attrs.get("scheduled_date", getattr(self.instance, "scheduled_date", None))
        if completed and scheduled and completed < scheduled:
            raise serializers.ValidationError(
                {"completed_date": "Completed date cannot precede the scheduled date."}
            )
        return attrs


class MaintenanceLogViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceLogSerializer
    filterset_fields = ["asset", "status", "maintenance_type"]
    ordering_fields = ["scheduled_date", "cost"]

    def get_queryset(self):
        return MaintenanceLog.objects.select_related("asset", "performed_by")

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsTechnicianOrAdmin()]
        return [IsAdminOnly()]


router = routers.DefaultRouter()
router.register("logs", MaintenanceLogViewSet, basename="maintenance-log")

urlpatterns = [path("", include(router.urls))]
