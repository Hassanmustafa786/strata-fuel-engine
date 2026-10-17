from rest_framework import serializers


class TripPlanRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200, trim_whitespace=True)
    destination = serializers.CharField(max_length=200, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["origin"].casefold() == attrs["destination"].casefold():
            raise serializers.ValidationError(
                "Origin and destination must be different."
            )
        return attrs
