from django.urls import path

from . import views

urlpatterns = [
    path("restock/", views.RestockQueueView.as_view(), name="restock-queue"),
    path("restock/<uuid:pk>/resolve/", views.resolve_alert, name="restock-resolve"),
]
