from django.urls import path

from . import views

urlpatterns = [
    path("", views.maintenance_list, name="maintenance-list"),
    path("new/", views.MaintenanceCreateView.as_view(), name="maintenance-create"),
    path("<uuid:pk>/edit/", views.MaintenanceUpdateView.as_view(), name="maintenance-update"),
    path("<uuid:pk>/complete/", views.maintenance_complete, name="maintenance-complete"),
]
