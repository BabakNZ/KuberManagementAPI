from rest_framework import serializers

from .models import Application


class ApplicationCreateSerializer(serializers.ModelSerializer):
    namespace_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "namespace_id",
            "name",
            "image",
            "replicas",
            "cpu_request",
            "cpu_limit",
            "memory_request",
            "memory_limit",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        import re

        if not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", value):
            raise serializers.ValidationError(
                "App name must be a valid RFC 1123 DNS label."
            )
        return value

    def validate_replicas(self, value):
        if value < 0:
            raise serializers.ValidationError("replicas cannot be negative.")
        return value


class ApplicationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = [
            "replicas",
            "image",
            "cpu_request",
            "cpu_limit",
            "memory_request",
            "memory_limit",
        ]
        extra_kwargs = {field: {"required": False} for field in fields}


class ApplicationSerializer(serializers.ModelSerializer):
    """Base desired-state representation (no live status)."""

    class Meta:
        model = Application
        fields = [
            "id",
            "namespace",
            "name",
            "image",
            "replicas",
            "cpu_request",
            "cpu_limit",
            "memory_request",
            "memory_limit",
            "status",
            "created_at",
            "updated_at",
        ]


class ApplicationWithLiveStatusSerializer(ApplicationSerializer):
    """
    Used for GET responses: desired state from the DB + a `live` block
    populated from Kubernetes at request time. See workloads/views.py for
    where `live` gets attached.
    """

    live = serializers.SerializerMethodField()

    class Meta(ApplicationSerializer.Meta):
        fields = ApplicationSerializer.Meta.fields + ["live"]

    def get_live(self, obj):
        return getattr(obj, "_live_status", None)
