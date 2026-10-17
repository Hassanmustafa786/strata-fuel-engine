from django.urls import path

from . import views

urlpatterns = [
    path("plan/", views.TripPlanView.as_view(), name="trip-plan"),
    path("map/", views.trip_map, name="trip-map"),
]
