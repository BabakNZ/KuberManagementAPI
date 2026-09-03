"""
Service layer for Namespace operations.
"""

import logging
from time import perf_counter

from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

from core.exceptions import NamespaceAlreadyExistsError, NamespaceNotFoundError
from core.k8s_client import api_client_for, translate_api_exception
from core.metrics import (
    kubernetes_operation_duration_seconds,
    kubernetes_operations_total,
)

logger = logging.getLogger(__name__)


def create_namespace_in_k8s(cluster, name: str) -> None:
    resource = "namespace"
    operation = "create"
    start = perf_counter()

    try:
        with api_client_for(cluster) as api:
            core_v1 = k8s.CoreV1Api(api)
            body = k8s.V1Namespace(
                metadata=k8s.V1ObjectMeta(name=name)
            )

            try:
                core_v1.create_namespace(
                    body,
                    _request_timeout=_timeout_or_none(),
                )
            except ApiException as exc:
                raise translate_api_exception(
                    exc,
                    not_found_exc=NamespaceNotFoundError,
                    conflict_exc=NamespaceAlreadyExistsError,
                ) from exc
            except Exception as exc:
                raise translate_api_exception(
                    exc,
                    not_found_exc=NamespaceNotFoundError,
                    conflict_exc=NamespaceAlreadyExistsError,
                ) from exc

    except Exception:
        kubernetes_operations_total.labels(
            resource=resource,
            operation=operation,
            outcome="error",
        ).inc()
        raise

    else:
        kubernetes_operations_total.labels(
            resource=resource,
            operation=operation,
            outcome="success",
        ).inc()

    finally:
        kubernetes_operation_duration_seconds.labels(
            resource=resource,
            operation=operation,
        ).observe(perf_counter() - start)


def delete_namespace_in_k8s(cluster, name: str) -> None:
    """Idempotent: a namespace that's already gone counts as success."""

    resource = "namespace"
    operation = "delete"
    start = perf_counter()

    try:
        with api_client_for(cluster) as api:
            core_v1 = k8s.CoreV1Api(api)

            try:
                core_v1.delete_namespace(
                    name,
                    _request_timeout=_timeout_or_none(),
                )

            except ApiException as exc:
                if exc.status == 404:
                    logger.info(
                        "Namespace %s already absent from cluster %s; "
                        "treating delete as successful (idempotent).",
                        name,
                        cluster.name,
                    )
                    return

                raise translate_api_exception(
                    exc,
                    not_found_exc=NamespaceNotFoundError,
                    conflict_exc=NamespaceAlreadyExistsError,
                ) from exc

            except Exception as exc:
                raise translate_api_exception(
                    exc,
                    not_found_exc=NamespaceNotFoundError,
                    conflict_exc=NamespaceAlreadyExistsError,
                ) from exc

    except Exception:
        kubernetes_operations_total.labels(
            resource=resource,
            operation=operation,
            outcome="error",
        ).inc()
        raise

    else:
        kubernetes_operations_total.labels(
            resource=resource,
            operation=operation,
            outcome="success",
        ).inc()

    finally:
        kubernetes_operation_duration_seconds.labels(
            resource=resource,
            operation=operation,
        ).observe(perf_counter() - start)


def namespace_exists_in_k8s(cluster, name: str) -> bool:
    resource = "namespace"
    operation = "read"
    start = perf_counter()

    try:
        with api_client_for(cluster) as api:
            core_v1 = k8s.CoreV1Api(api)

            try:
                core_v1.read_namespace(
                    name,
                    _request_timeout=_timeout_or_none(),
                )
                result = True

            except ApiException as exc:
                if exc.status == 404:
                    result = False
                else:
                    raise translate_api_exception(
                        exc,
                        not_found_exc=NamespaceNotFoundError,
                        conflict_exc=NamespaceAlreadyExistsError,
                    ) from exc

    except Exception:
        kubernetes_operations_total.labels(
            resource=resource,
            operation=operation,
            outcome="error",
        ).inc()
        raise

    else:
        kubernetes_operations_total.labels(
            resource=resource,
            operation=operation,
            outcome="success",
        ).inc()
        return result

    finally:
        kubernetes_operation_duration_seconds.labels(
            resource=resource,
            operation=operation,
        ).observe(perf_counter() - start)


def _timeout_or_none():
    from django.conf import settings

    return settings.K8S_REQUEST_TIMEOUT_SECONDS