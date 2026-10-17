class TripPlanningError(Exception):
    """Base class for errors shown to API clients."""


class LocationNotFound(TripPlanningError):
    pass


class RouteNotFound(TripPlanningError):
    pass


class ExternalServiceError(TripPlanningError):
    """A free geocoding/routing service failed or timed out."""
