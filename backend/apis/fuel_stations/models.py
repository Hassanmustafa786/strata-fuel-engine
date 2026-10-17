from django.db import models

# Create your models here.
class FuelStation(models.Model):
    opis_truckstop_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.BigIntegerField(null=True, blank=True)

    retail_price = models.DecimalField(
        max_digits=8,
        decimal_places=5,
    )

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class GeocodeStatus(models.TextChoices):
        SUCCESS = "success", "Success"
        # Coordinates are the centroid of the station's city.
        APPROXIMATE = "approximate", "Approximate (city centroid)"
        NOT_FOUND = "not_found", "Not found"
        ERROR = "error", "Error"

    # NULL means geocoding has not been attempted yet.
    geocode_status = models.CharField(
        max_length=20,
        choices=GeocodeStatus.choices,
        null=True,
        blank=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fuel_stations"

        indexes = [
            models.Index(fields=["state", "retail_price"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "name",
                    "address",
                    "city",
                    "state",
                    "rack_id",
                ],
                name="uniq_fuel_station_identity",
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state}"