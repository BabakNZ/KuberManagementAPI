import logging

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from clusters.models import Cluster
from core.exceptions import (
    ClusterNotFoundError,
    NamespaceAlreadyExistsError,
    NamespaceOperationInProgressError,
)

from .models import Namespace
from .serializers import NamespaceCreateSerializer, NamespaceSerializer
from .services import create_namespace_in_k8s, delete_namespace_in_k8s

logger = logging.getLogger(__name__)


class NamespaceListCreateView(APIView):
    """
    GET  /api/namespaces/?cluster_id=5  -> namespaces THIS backend created
                                            for that cluster (DB is source
                                            of truth, per spec).
    POST /api/namespaces/               -> create in Kubernetes, then
                                            persist to DB.
    """

    throttle_scope = "namespace-write"

    def get(self, request):
        cluster_id = request.query_params.get("cluster_id")
        if not cluster_id:
            raise ValidationError({"cluster_id": "This query parameter is required."})
        queryset = Namespace.objects.filter(
            cluster_id=cluster_id, status=Namespace.STATUS_ACTIVE
        )
        return Response(NamespaceSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = NamespaceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cluster_id = serializer.validated_data["cluster_id"]
        name = serializer.validated_data["name"]

        try:
            cluster = Cluster.objects.get(pk=cluster_id)
        except Cluster.DoesNotExist:
            raise ClusterNotFoundError() from None

        if Namespace.objects.filter(
            cluster=cluster, name=name, status=Namespace.STATUS_ACTIVE
        ).exists():
            raise NamespaceAlreadyExistsError(
                "This backend has already created a namespace with this "
                "name on this cluster."
            )

        # 1. Create in Kubernetes first.
        create_namespace_in_k8s(cluster, name)

        # 2. Persist to DB. If this fails, compensate by removing the
        #    Kubernetes namespace we just created, so we don't leave an
        #    orphan that the DB (source of truth) doesn't know about.
        try:
            with transaction.atomic():
                namespace = Namespace.objects.create(
                    cluster=cluster, name=name, status=Namespace.STATUS_ACTIVE
                )
        except IntegrityError:
            logger.error(
                "DB write failed after Kubernetes namespace '%s' was created "
                "on cluster '%s'; attempting compensating delete.",
                name,
                cluster.name,
            )
            try:
                delete_namespace_in_k8s(cluster, name)
            except Exception:
                logger.exception(
                    "Compensating delete FAILED for orphaned namespace '%s' "
                    "on cluster '%s'. Manual reconciliation required.",
                    name,
                    cluster.name,
                )
            raise NamespaceAlreadyExistsError(
                "Namespace record already exists (concurrent create)."
            ) from None

        return Response(
            NamespaceSerializer(namespace).data, status=status.HTTP_201_CREATED
        )


class NamespaceDetailView(APIView):
    """
    DELETE /api/namespaces/<id>/

    Concurrency-safe delete:
      1. Lock the row and flip active -> deleting inside a short
         transaction (released before any network call). A second,
         concurrent DELETE arriving while this is in flight sees
         status == deleting and gets 409 Conflict without touching
         Kubernetes.
      2. Delete from Kubernetes (idempotent - 404 counts as success).
      3. Delete the DB row. If step 2 succeeded but the process crashes
         before step 3, the row is left in `deleting` - a reconciliation
         pass (cron/Celery beat in production) would detect that the
         namespace is gone from Kubernetes and clean up the row.
    """

    throttle_scope = "namespace-write"

    def delete(self, request, pk):
        with transaction.atomic():
            namespace = get_object_or_404(
                Namespace.objects.select_for_update(), pk=pk
            )
            if namespace.status == Namespace.STATUS_DELETING:
                raise NamespaceOperationInProgressError()
            namespace.status = Namespace.STATUS_DELETING
            namespace.save(update_fields=["status", "updated_at"])
            cluster = namespace.cluster

        try:
            delete_namespace_in_k8s(cluster, namespace.name)
        except Exception:
            # Roll back to active so the namespace isn't stuck "deleting"
            # forever and the caller can retry.
            namespace.status = Namespace.STATUS_ACTIVE
            namespace.save(update_fields=["status", "updated_at"])
            raise

        namespace.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
