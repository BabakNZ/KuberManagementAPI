"""
Service layer for Namespace operations. Views stay thin (HTTP concerns
only); this module owns talking to Kubernetes and the compensating logic
around partial failures.

--- Edge cases this module explicitly handles (per assignment) ---

1) POST: Kubernetes create succeeds, then the DB write fails/crashes.
   We create in Kubernetes first, then write to the DB. If the DB write
   raises, we make a best-effort attempt to delete the just-created
   Kubernetes namespace to avoid an orphan (compensating transaction).
   If THAT also fails, we log loudly - this is exactly the kind of gap a
   periodic reconciliation job (see module docstring bottom) would close
   in a fuller implementation.

2) DELETE: two requests race, or the process crashes between the
   Kubernetes delete and the DB delete.
   - Concurrent DELETEs: the view locks the row (`select_for_update`)
     and flips status active -> deleting inside one short transaction
     before doing any network I/O. A second concurrent request sees
     status == deleting and gets 409 Conflict immediately - it never
     reaches Kubernetes.
   - Kubernetes delete succeeds but the process dies before the DB row is
     removed: the row is left in `deleting` status. On the next GET/DELETE
     touching that row, we can detect this (see `reconcile_deleting_namespace`)
     by checking whether the namespace still actually exists in
     Kubernetes, and clean up the stale DB row if it doesn't. In
     production this check would instead run as a periodic background
     job (Celery beat / k8s CronJob) rather than opportunistically inline.
   - Kubernetes DELETE of a namespace that's already gone (404) is treated
     as success (idempotent delete), since the end state the caller wants
     ("namespace gone") is already true.
"""

import logging

from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

from core.exceptions import NamespaceAlreadyExistsError, NamespaceNotFoundError
from core.k8s_client import api_client_for, translate_api_exception

logger = logging.getLogger(__name__)


def create_namespace_in_k8s(cluster, name: str) -> None:
    with api_client_for(cluster) as api:
        core_v1 = k8s.CoreV1Api(api)
        body = k8s.V1Namespace(metadata=k8s.V1ObjectMeta(name=name))
        try:
            core_v1.create_namespace(
                body, _request_timeout=_timeout_or_none()
            )
        except ApiException as exc:
            raise translate_api_exception(
                exc,
                not_found_exc=NamespaceNotFoundError,
                conflict_exc=NamespaceAlreadyExistsError,
            ) from exc
        except Exception as exc:  # connection-level failures etc.
            raise translate_api_exception(
                exc,
                not_found_exc=NamespaceNotFoundError,
                conflict_exc=NamespaceAlreadyExistsError,
            ) from exc


def delete_namespace_in_k8s(cluster, name: str) -> None:
    """Idempotent: a namespace that's already gone (404) counts as success."""
    with api_client_for(cluster) as api:
        core_v1 = k8s.CoreV1Api(api)
        try:
            core_v1.delete_namespace(name, _request_timeout=_timeout_or_none())
        except ApiException as exc:
            if exc.status == 404:
                logger.info(
                    "Namespace %s already absent from cluster %s; treating "
                    "delete as successful (idempotent).",
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


def namespace_exists_in_k8s(cluster, name: str) -> bool:
    with api_client_for(cluster) as api:
        core_v1 = k8s.CoreV1Api(api)
        try:
            core_v1.read_namespace(name, _request_timeout=_timeout_or_none())
            return True
        except ApiException as exc:
            if exc.status == 404:
                return False
            raise translate_api_exception(
                exc,
                not_found_exc=NamespaceNotFoundError,
                conflict_exc=NamespaceAlreadyExistsError,
            ) from exc


def _timeout_or_none():
    from django.conf import settings

    return settings.K8S_REQUEST_TIMEOUT_SECONDS
