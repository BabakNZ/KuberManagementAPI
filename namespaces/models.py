from django.db import models

from clusters.models import Cluster


class Namespace(models.Model):
    """
    Source of truth for "which namespaces did THIS backend create" is this
    table, not live Kubernetes state (per spec: a namespace someone else
    created directly in the cluster must never show up here).

    `status` exists specifically to make DELETE safe under concurrency and
    partial failure:
      - active    : normal state, fully in sync with Kubernetes
      - deleting  : a delete is in flight (used to reject a second
                    concurrent delete with 409 instead of doing it twice)
      - failed    : Kubernetes delete succeeded but the DB delete that
                    should have followed it crashed/failed; needs
                    reconciliation (see namespaces/services.py docstring)
    """

    STATUS_ACTIVE = "active"
    STATUS_DELETING = "deleting"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_DELETING, "Deleting"),
        (STATUS_FAILED, "Failed"),
    ]

    cluster = models.ForeignKey(
        Cluster, related_name="namespaces", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cluster", "name"], name="unique_namespace_per_cluster"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.name}"
