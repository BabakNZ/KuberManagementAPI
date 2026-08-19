"""
Domain-level exceptions raised by the k8s service layers (namespaces,
workloads), plus a DRF exception handler that maps each one to the HTTP
status code called for in the spec:

  400 Bad Request      - invalid input
  401 Unauthorized      - auth failure (reserved for future use)
  403 Forbidden          - backend's k8s credentials lack permission
  404 Not Found           - cluster/namespace/app not found
  409 Conflict              - resource already exists / concurrent op in flight
  500 Internal Server Error - unexpected backend error
  502 Bad Gateway            - the Kubernetes API itself is unreachable/erroring

Keeping these as plain Python exceptions (rather than DRF exceptions)
means the service layer (core/k8s_client.py, namespaces/services.py,
workloads/services.py) has zero dependency on the web framework and can
be reused from a management command, a Celery task, etc.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Base class for all domain/service-layer errors."""

    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "An unexpected error occurred."
    error_code = "internal_error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class ClusterNotFoundError(DomainError):
    http_status = status.HTTP_404_NOT_FOUND
    default_detail = "Cluster not found."
    error_code = "cluster_not_found"


class ClusterUnreachableError(DomainError):
    http_status = status.HTTP_502_BAD_GATEWAY
    default_detail = "Kubernetes API for this cluster is unreachable."
    error_code = "cluster_unreachable"


class KubernetesForbiddenError(DomainError):
    http_status = status.HTTP_403_FORBIDDEN
    default_detail = "The backend's credentials are not permitted to perform this action on the cluster."
    error_code = "kubernetes_forbidden"


class NamespaceNotFoundError(DomainError):
    http_status = status.HTTP_404_NOT_FOUND
    default_detail = "Namespace not found."
    error_code = "namespace_not_found"


class NamespaceAlreadyExistsError(DomainError):
    http_status = status.HTTP_409_CONFLICT
    default_detail = "Namespace already exists on this cluster."
    error_code = "namespace_already_exists"


class NamespaceOperationInProgressError(DomainError):
    http_status = status.HTTP_409_CONFLICT
    default_detail = "A delete operation for this namespace is already in progress."
    error_code = "namespace_operation_in_progress"


class ApplicationNotFoundError(DomainError):
    http_status = status.HTTP_404_NOT_FOUND
    default_detail = "Application not found."
    error_code = "application_not_found"


class ApplicationAlreadyExistsError(DomainError):
    http_status = status.HTTP_409_CONFLICT
    default_detail = "An application with this name already exists in this namespace."
    error_code = "application_already_exists"


class ApplicationOperationInProgressError(DomainError):
    http_status = status.HTTP_409_CONFLICT
    default_detail = "An operation for this application is already in progress."
    error_code = "application_operation_in_progress"


def custom_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        logger.warning("Domain error: %s (%s)", exc.detail, exc.error_code)
        return Response(
            {"error": exc.error_code, "detail": exc.detail},
            status=exc.http_status,
        )

    # Fall back to DRF's default handling for framework-level exceptions
    # (ValidationError, NotAuthenticated, Throttled, etc.)
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled exception")
    return response
