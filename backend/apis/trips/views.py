import logging

from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TripPlanRequestSerializer
from .services.errors import (
    ExternalServiceError,
    LocationNotFound,
    RouteNotFound,
)
from .services.planner import plan_trip

logger = logging.getLogger(__name__)


class TripPlanView(APIView):
    """
    POST {"origin": "Chicago, IL", "destination": "Denver, CO"}

    Returns the route geometry, recommended fuel stops and total fuel
    cost. Locations may also be given as "latitude, longitude".
    """

    def http_method_not_allowed(self, request, *args, **kwargs):
        return Response(
            {
                "status": False,
                "message": f'Method "{request.method}" not allowed.',
                "data": {
                    "detail": "Use POST for this endpoint.",
                    "code": "method_not_allowed",
                },
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def post(self, request):
        try:
            serializer = TripPlanRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": False,
                        "message": "Invalid request.",
                        "data": {
                            "detail": serializer.errors,
                            "code": "validation_error",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            plan = plan_trip(**serializer.validated_data)
            fuel_plan = plan["fuel_plan"]
            message = (
                "Trip planned successfully." if fuel_plan["feasible"]
                else "Route found, but no complete fuel plan: "
                f"{fuel_plan['message']}"
            )
            return Response(
                {"status": True, "message": message, "data": plan},
                status=status.HTTP_200_OK,
            )

        except ParseError as exc:
            return Response(
                {
                    "status": False,
                    "message": "Request body is not valid JSON.",
                    "data": {"detail": str(exc.detail), "code": "parse_error"},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except LocationNotFound as exc:
            return Response(
                {
                    "status": False,
                    "message": "Location not found.",
                    "data": {"detail": str(exc), "code": "location_not_found"},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RouteNotFound as exc:
            return Response(
                {
                    "status": False,
                    "message": "No route found.",
                    "data": {"detail": str(exc), "code": "route_not_found"},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except ExternalServiceError as exc:
            return Response(
                {
                    "status": False,
                    "message": "Map service is unavailable. Please try again.",
                    "data": {"detail": str(exc), "code": "upstream_error"},
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            # Keep the traceback in the server log, not in the response.
            logger.exception("Trip planning failed")
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
