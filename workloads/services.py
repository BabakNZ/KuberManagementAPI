"""
Service layer for Application (Deployment) operations.

Design decisions called out by the spec:

- Pod/App status is ALWAYS read live from Kubernetes (never from the DB).
  `get_live_status` lists Pods by label selector `app=<name>` and reports
  both the per-pod detail and an aggregated status, so a consumer (UI) can
  show either "2/3 ready" or a single rolled-up "Not Ready" badge -
  whichever the frontend prefers; we don't collapse that decision here.
- App-level `status` in the DB (creating/active/updating/deleting/failed)
  tracks the backend's own reconciliation state (e.g. "is our last
  Kubernetes call still in flight / did it fail"), which is a different
  axis from live Pod readiness and is kept separate deliberately.
"""

import logging

from kubernetes import client as k8s
from kubernetes.client.rest import ApiException

from core.exceptions import (
    ApplicationAlreadyExistsError,
    ApplicationNotFoundError,
)
from core.k8s_client import api_client_for, translate_api_exception

logger = logging.getLogger(__name__)


def _resources(app) -> k8s.V1ResourceRequirements:
    return k8s.V1ResourceRequirements(
        requests={"cpu": app.cpu_request, "memory": app.memory_request},
        limits={"cpu": app.cpu_limit, "memory": app.memory_limit},
    )


def _build_deployment_manifest(app) -> k8s.V1Deployment:
    labels = {"app": app.name}
    container = k8s.V1Container(
        name=app.name,
        image=app.image,
        resources=_resources(app),
        ports=[k8s.V1ContainerPort(container_port=8080)],
    )
    template = k8s.V1PodTemplateSpec(
        metadata=k8s.V1ObjectMeta(labels=labels),
        spec=k8s.V1PodSpec(containers=[container]),
    )
    spec = k8s.V1DeploymentSpec(
        replicas=app.replicas,
        selector=k8s.V1LabelSelector(match_labels=labels),
        template=template,
    )
    return k8s.V1Deployment(
        metadata=k8s.V1ObjectMeta(name=app.name, labels=labels),
        spec=spec,
    )


def create_deployment_in_k8s(app) -> None:
    with api_client_for(app.namespace.cluster) as api:
        apps_v1 = k8s.AppsV1Api(api)
        try:
            apps_v1.create_namespaced_deployment(
                namespace=app.namespace.name,
                body=_build_deployment_manifest(app),
                _request_timeout=_timeout_or_none(),
            )
        except (ApiException, Exception) as exc:
            raise translate_api_exception(
                exc,
                not_found_exc=ApplicationNotFoundError,
                conflict_exc=ApplicationAlreadyExistsError,
            ) from exc


def update_deployment_in_k8s(app) -> None:
    """Patches replicas/resources on the existing Deployment."""
    with api_client_for(app.namespace.cluster) as api:
        apps_v1 = k8s.AppsV1Api(api)
        patch_body = {
            "spec": {
                "replicas": app.replicas,
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": app.name,
                                "image": app.image,
                                "resources": {
                                    "requests": {
                                        "cpu": app.cpu_request,
                                        "memory": app.memory_request,
                                    },
                                    "limits": {
                                        "cpu": app.cpu_limit,
                                        "memory": app.memory_limit,
                                    },
                                },
                            }
                        ]
                    }
                },
            }
        }
        try:
            apps_v1.patch_namespaced_deployment(
                name=app.k8s_deployment_name,
                namespace=app.namespace.name,
                body=patch_body,
                _request_timeout=_timeout_or_none(),
            )
        except (ApiException, Exception) as exc:
            raise translate_api_exception(
                exc,
                not_found_exc=ApplicationNotFoundError,
                conflict_exc=ApplicationAlreadyExistsError,
            ) from exc


def delete_deployment_in_k8s(app) -> None:
    """Idempotent: a Deployment that's already gone (404) counts as success."""
    with api_client_for(app.namespace.cluster) as api:
        apps_v1 = k8s.AppsV1Api(api)
        try:
            apps_v1.delete_namespaced_deployment(
                name=app.k8s_deployment_name,
                namespace=app.namespace.name,
                _request_timeout=_timeout_or_none(),
            )
        except ApiException as exc:
            if exc.status == 404:
                logger.info(
                    "Deployment %s already absent from namespace %s; "
                    "treating delete as successful (idempotent).",
                    app.name,
                    app.namespace.name,
                )
                return
            raise translate_api_exception(
                exc,
                not_found_exc=ApplicationNotFoundError,
                conflict_exc=ApplicationAlreadyExistsError,
            ) from exc
        except Exception as exc:
            raise translate_api_exception(
                exc,
                not_found_exc=ApplicationNotFoundError,
                conflict_exc=ApplicationAlreadyExistsError,
            ) from exc


def get_live_status(app) -> dict:
    """
    Reads Pod status live from Kubernetes for this app. Never touches the
    DB for status - only for desired-state fields (image, replicas, etc.)
    which the caller already has on `app`.
    """
    with api_client_for(app.namespace.cluster) as api:
        core_v1 = k8s.CoreV1Api(api)
        try:
            pods = core_v1.list_namespaced_pod(
                namespace=app.namespace.name,
                label_selector=app.k8s_label_selector,
                _request_timeout=_timeout_or_none(),
            )
        except (ApiException, Exception) as exc:
            raise translate_api_exception(
                exc,
                not_found_exc=ApplicationNotFoundError,
                conflict_exc=ApplicationAlreadyExistsError,
            ) from exc

    pod_statuses = []
    for pod in pods.items:
        ready = False
        if pod.status and pod.status.conditions:
            ready = any(
                c.type == "Ready" and c.status == "True" for c in pod.status.conditions
            )
        pod_statuses.append(
            {
                "name": pod.metadata.name,
                "phase": pod.status.phase if pod.status else "Unknown",
                "ready": ready,
            }
        )

    # Aggregate: the app is only "Ready" if every pod is ready and the pod
    # count matches desired replicas. Exposed alongside per-pod detail so
    # the frontend can render either view.
    all_ready = bool(pod_statuses) and all(p["ready"] for p in pod_statuses)
    ready_count = sum(1 for p in pod_statuses if p["ready"])

    return {
        "ready": all_ready and ready_count == app.replicas,
        "ready_replicas": ready_count,
        "desired_replicas": app.replicas,
        "pods": pod_statuses,
    }


def _timeout_or_none():
    from django.conf import settings

    return settings.K8S_REQUEST_TIMEOUT_SECONDS
