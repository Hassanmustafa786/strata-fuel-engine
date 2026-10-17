import logging

from django.db.models import Count, Q
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation

logger = logging.getLogger(__name__)


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

    def list(self, request, *args, **kwargs):
        try:
            page = self.paginate_queryset(self.get_queryset())
            serializer = self.get_serializer(page, many=True)
            return Response(
                {
                    "status": True,
                    "message": "Fuel stations retrieved.",
                    "data": {
                        "count": self.paginator.page.paginator.count,
                        "next": self.paginator.get_next_link(),
                        "previous": self.paginator.get_previous_link(),
                        "results": serializer.data,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except NotFound as exc:
            # Page number past the last page.
            return Response(
                {
                    "status": False,
                    "message": "Page not found.",
                    "data": {"detail": str(exc.detail), "code": "not_found"},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("Listing fuel stations failed")
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong. Please try again.",
                    "data": {
                        "detail": "Internal server error.",
                        "code": "server_error",
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class HealthView(APIView):
    def get(self, request):
        try:
            counts = FuelStation.objects.aggregate(
                stations=Count("id"),
                geocoded=Count("id", filter=Q(latitude__isnull=False)),
            )
            return Response(
                {
                    "status": True,
                    "message": "Service is running.",
                    "data": counts,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception("Health check failed")
            return Response(
                {
                    "status": False,
                    "message": "Service is unhealthy.",
                    "data": {
                        "detail": "Database is unavailable.",
                        "code": "server_error",
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
