from django.urls import path

from . import views

urlpatterns = [
    path("", views.FuelStationListView.as_view(), name="fuel-station-list"),
]
