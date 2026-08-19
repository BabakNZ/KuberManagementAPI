from rest_framework import serializers

from .models import Cluster


class ClusterCreateSerializer(serializers.ModelSerializer):
    """
    Used for POST only. `token` is write_only so it can never leak back out
    through this serializer's .data, even by accident.
    """

    token = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = Cluster
        fields = ["id", "name", "address", "token", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        raw_token = validated_data.pop("token")
        cluster = Cluster(**validated_data)
        cluster.set_token(raw_token)
        cluster.save()
        return cluster


class ClusterListSerializer(serializers.ModelSerializer):
    """
    Used for GET. Deliberately excludes both `token` and `encrypted_token` -
    the spec is explicit that the token must never appear in a response.
    """

    class Meta:
        model = Cluster
        fields = ["id", "name", "address", "created_at", "updated_at"]
