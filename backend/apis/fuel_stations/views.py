from django.db.models import Count, Q
from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation


class FuelStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelStation
        fields = [
            "id", "opis_truckstop_id", "name", "address", "city", "state",
            "rack_id", "retail_price", "latitude", "longitude",
            "geocode_status",
        ]


class StationPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class FuelStationListView(generics.ListAPIView):
    """
    Stations for debugging. Filters: ?state=TX, ?geocoded=true,
    ?ordering=retail_price.
    """
    serializer_class = FuelStationSerializer
    pagination_class = StationPagination
    ordering_fields = {"retail_price", "state", "city", "name", "id"}

    def get_queryset(self):
        params = self.request.query_params
        queryset = FuelStation.objects.all()

        if state := params.get("state"):
            queryset = queryset.filter(state=state.upper())

        geocoded = params.get("geocoded")
        if geocoded in {"true", "false"}:
            queryset = queryset.filter(latitude__isnull=geocoded == "false")

        ordering = params.get("ordering", "id")
        if ordering.lstrip("-") not in self.ordering_fields:
            ordering = "id"

        return queryset.order_by(ordering)


class HealthView(APIView):
    def get(self, request):
        counts = FuelStation.objects.aggregate(
            stations=Count("id"),
            geocoded=Count("id", filter=Q(latitude__isnull=False)),
        )
        return Response({"status": "ok", **counts})
