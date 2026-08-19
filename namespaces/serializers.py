from rest_framework import serializers

from .models import Namespace


class NamespaceCreateSerializer(serializers.Serializer):
    cluster_id = serializers.IntegerField()
    name = serializers.RegexField(
        # Kubernetes namespace names are RFC 1123 DNS labels.
        regex=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        max_length=63,
        error_messages={
            "invalid": (
                "Namespace name must be a valid RFC 1123 DNS label: "
                "lowercase alphanumeric characters or '-', starting and "
                "ending with an alphanumeric character."
            )
        },
    )


class NamespaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Namespace
        fields = ["id", "cluster", "name", "status", "created_at", "updated_at"]
