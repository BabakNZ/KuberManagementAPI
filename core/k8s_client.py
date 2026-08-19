"""
Builds a Kubernetes API client at request time from a `clusters.Cluster`
row (address + bearer token), rather than from a static kubeconfig file.

This is what lets the backend manage an arbitrary number of clusters -
today just your one k3s cluster, tomorrow more - purely by adding rows to
the Cluster table, with no redeploy needed.
"""

from contextlib import contextmanager

import urllib3
from django.conf import settings
from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError, NewConnectionError

from core.exceptions import ClusterUnreachableError, KubernetesForbiddenError

# We intentionally allow self-signed certs (typical for k3s) unless the
# operator explicitly configures verification. Suppress the resulting
# urllib3 warning noise; the trust decision itself is made via
# settings.K8S_VERIFY_SSL / K8S_CA_CERT_PATH.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _build_configuration(cluster) -> k8s_client.Configuration:
    address = cluster.address.strip()
    if not address.startswith("http://") and not address.startswith("https://"):
        address = f"https://{address}"

    config = k8s_client.Configuration()
    config.host = address
    config.api_key = {"authorization": cluster.get_token()}
    config.api_key_prefix = {"authorization": "Bearer"}
    config.verify_ssl = settings.K8S_VERIFY_SSL
    if settings.K8S_CA_CERT_PATH:
        config.ssl_ca_cert = settings.K8S_CA_CERT_PATH
    return config


@contextmanager
def api_client_for(cluster):
    """
    Usage:
        with api_client_for(cluster) as api:
            core_v1 = k8s_client.CoreV1Api(api)
            ...
    """
    configuration = _build_configuration(cluster)
    api = k8s_client.ApiClient(configuration)
    try:
        yield api
    finally:
        api.close()


def translate_api_exception(exc: Exception, *, not_found_exc, conflict_exc):
    """
    Central place mapping kubernetes-client exceptions to our domain
    exceptions, so every service function doesn't reimplement this.

    `not_found_exc` / `conflict_exc` let each call site provide the
    resource-specific exception (NamespaceNotFoundError vs
    ApplicationNotFoundError, etc.) while still sharing this logic.
    """
    if isinstance(exc, ApiException):
        if exc.status == 404:
            return not_found_exc()
        if exc.status == 409:
            return conflict_exc()
        if exc.status == 403:
            return KubernetesForbiddenError()
        if exc.status and exc.status >= 500:
            return ClusterUnreachableError(f"Kubernetes API error: {exc.reason}")
        return ClusterUnreachableError(f"Kubernetes API error ({exc.status}): {exc.reason}")

    if isinstance(exc, (MaxRetryError, NewConnectionError, ConnectionError, TimeoutError)):
        return ClusterUnreachableError("Could not connect to the cluster's Kubernetes API.")

    # Unknown error shape - still surface as a gateway error rather than a
    # raw 500, since the trigger was a downstream Kubernetes call.
    return ClusterUnreachableError(f"Unexpected error talking to Kubernetes: {exc}")
