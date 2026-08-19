from django.db import models

from namespaces.models import Namespace


class Application(models.Model):
    """
    Desired-state record for an App (backed by a Kubernetes Deployment).

    Only *desired* state lives here (image, replicas, resources). Actual
    Pod/Deployment status is always read live from Kubernetes at request
    time (see workloads/services.get_live_status) and never cached in this
    table - the spec is explicit that status must not be read from the
    database.
    """

    STATUS_CREATING = "creating"
    STATUS_ACTIVE = "active"
    STATUS_UPDATING = "updating"
    STATUS_DELETING = "deleting"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_CREATING, "Creating"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_UPDATING, "Updating"),
        (STATUS_DELETING, "Deleting"),
        (STATUS_FAILED, "Failed"),
    ]

    namespace = models.ForeignKey(
        Namespace, related_name="apps", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    image = models.CharField(max_length=500)
    replicas = models.PositiveIntegerField(default=1)

    cpu_request = models.CharField(max_length=20, default="100m")
    cpu_limit = models.CharField(max_length=20, default="500m")
    memory_request = models.CharField(max_length=20, default="128Mi")
    memory_limit = models.CharField(max_length=20, default="512Mi")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATING
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["namespace", "name"], name="unique_app_per_namespace"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.namespace}/{self.name}"

    @property
    def k8s_deployment_name(self) -> str:
        return self.name

    @property
    def k8s_label_selector(self) -> str:
        return f"app={self.name}"
