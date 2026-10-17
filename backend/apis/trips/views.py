from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TripPlanRequestSerializer
from .services.errors import (
    ExternalServiceError,
    LocationNotFound,
    RouteNotFound,
)
from .services.planner import plan_trip

ERROR_STATUS = {
    LocationNotFound: (status.HTTP_400_BAD_REQUEST, "location_not_found"),
    RouteNotFound: (status.HTTP_422_UNPROCESSABLE_ENTITY, "route_not_found"),
    ExternalServiceError: (status.HTTP_502_BAD_GATEWAY, "upstream_error"),
}


def _plan_or_error(data):
    """Return (plan, None) or (None, (http_status, error_body))."""
    serializer = TripPlanRequestSerializer(data=data)
    if not serializer.is_valid():
        return None, (status.HTTP_400_BAD_REQUEST, serializer.errors)

    try:
        return plan_trip(**serializer.validated_data), None
    except tuple(ERROR_STATUS) as exc:
        http_status, code = ERROR_STATUS[type(exc)]
        return None, (http_status, {"detail": str(exc), "code": code})


class TripPlanView(APIView):
    """
    POST {"origin": "Chicago, IL", "destination": "Denver, CO"}

    Returns the route geometry, recommended fuel stops and total fuel
    cost. Locations may also be given as "latitude, longitude".
    """

    def post(self, request):
        plan, error = _plan_or_error(request.data)
        if error:
            return Response(error[1], status=error[0])
        return Response(plan)


def trip_map(request):
    """GET ?origin=...&destination=... renders the plan on a map."""
    context = {"query": request.GET}
    http_status = status.HTTP_200_OK

    if request.GET:
        context["plan"], error = _plan_or_error(request.GET)
        if error:
            http_status, body = error
            context["error"] = body.get(
                "detail", "Enter two different locations."
            )

    return render(request, "trips/map.html", context, status=http_status)
