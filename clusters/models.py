from django.db import models

from core.encryption import decrypt_value, encrypt_value


class Cluster(models.Model):
    """
    Represents a Kubernetes cluster the backend is allowed to manage.

    Per the spec: POST /api/clusters/ ONLY persists this row. It must NOT
    connect to Kubernetes, verify the address, or check the token - that
    happens lazily, the first time a Namespace/App operation needs this
    cluster.
    """

    name = models.CharField(max_length=255, unique=True)
    address = models.CharField(
        max_length=255,
        help_text="Kubernetes API server address, e.g. 95.43.54.43:6443",
    )
    # Never store the raw token. Always go through set_token()/get_token().
    # blank=True so the Django admin (which deliberately hides this field,
    # see clusters/admin.py) can still save a Cluster row; real token
    # provisioning should go through POST /api/clusters/.
    encrypted_token = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def set_token(self, raw_token: str) -> None:
        self.encrypted_token = encrypt_value(raw_token)

    def get_token(self) -> str:
        return decrypt_value(self.encrypted_token)
