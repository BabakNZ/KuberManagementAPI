import logging

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import (
    ApplicationAlreadyExistsError,
    ApplicationOperationInProgressError,
    NamespaceNotFoundError,
)
from namespaces.models import Namespace

from .models import Application
from .serializers import (
    ApplicationCreateSerializer,
    ApplicationSerializer,
    ApplicationUpdateSerializer,
    ApplicationWithLiveStatusSerializer,
)
from .services import (
    create_deployment_in_k8s,
    delete_deployment_in_k8s,
    get_live_status,
    update_deployment_in_k8s,
)

logger = logging.getLogger(__name__)


def _attach_live_status(app: Application) -> Application:
    """
    Best-effort: if the cluster is briefly unreachable we still want GET to
    return the desired-state record rather than a hard 502, with `live`
    reported as unavailable. Write endpoints (create/update/delete) do
    propagate k8s errors, since those genuinely failed to apply.
    """
    try:
        app._live_status = get_live_status(app)
    except Exception as exc:
        logger.warning("Could not fetch live status for app %s: %s", app.id, exc)
        app._live_status = {"error": "live status unavailable", "detail": str(exc)}
    return app


class ApplicationListCreateView(APIView):
    """
    GET  /api/apps/?namespace_id=3  -> apps in that namespace, desired
                                        state + live Kubernetes status.
    POST /api/apps/                 -> create Deployment, then persist.
    """

    throttle_scope = "app-write"

    def get(self, request):
        namespace_id = request.query_params.get("namespace_id")
        if not namespace_id:
            raise ValidationError({"namespace_id": "This query parameter is required."})
        queryset = Application.objects.filter(namespace_id=namespace_id).select_related(
            "namespace", "namespace__cluster"
        )
        apps = [_attach_live_status(app) for app in queryset]
        return Response(ApplicationWithLiveStatusSerializer(apps, many=True).data)

    def post(self, request):
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        namespace_id = data.pop("namespace_id")

        try:
            namespace = Namespace.objects.select_related("cluster").get(
                pk=namespace_id, status=Namespace.STATUS_ACTIVE
            )
        except Namespace.DoesNotExist:
            raise NamespaceNotFoundError() from None

        if Application.objects.filter(namespace=namespace, name=data["name"]).exists():
            raise ApplicationAlreadyExistsError()

        app = Application(namespace=namespace, status=Application.STATUS_CREATING, **data)

        # Create in Kubernetes first, then persist - same rationale as
        # namespaces: the DB should never claim ownership of something
        # that doesn't actually exist in the cluster.
        create_deployment_in_k8s(app)

        try:
            with transaction.atomic():
                app.status = Application.STATUS_ACTIVE
                app.save()
        except IntegrityError:
            logger.error(
                "DB write failed after Deployment '%s' was created in "
                "namespace '%s'; attempting compensating delete.",
                app.name,
                namespace.name,
            )
            try:
                delete_deployment_in_k8s(app)
            except Exception:
                logger.exception(
                    "Compensating delete FAILED for orphaned Deployment "
                    "'%s' in namespace '%s'. Manual reconciliation required.",
                    app.name,
                    namespace.name,
                )
            raise ApplicationAlreadyExistsError(
                "Application record already exists (concurrent create)."
            ) from None

        return Response(
            ApplicationSerializer(app).data, status=status.HTTP_201_CREATED
        )


class ApplicationDetailView(APIView):
    """
    GET    /api/apps/<id>/  -> desired state + live status
    PATCH  /api/apps/<id>/  -> update replicas/image/resources
    DELETE /api/apps/<id>/  -> remove Deployment + DB row
    """

    throttle_scope = "app-write"

    def get(self, request, pk):
        app = get_object_or_404(
            Application.objects.select_related("namespace", "namespace__cluster"), pk=pk
        )
        _attach_live_status(app)
        return Response(ApplicationWithLiveStatusSerializer(app).data)

    def patch(self, request, pk):
        app = get_object_or_404(
            Application.objects.select_related("namespace", "namespace__cluster"), pk=pk
        )
        if app.status in (Application.STATUS_UPDATING, Application.STATUS_DELETING):
            raise ApplicationOperationInProgressError()

        serializer = ApplicationUpdateSerializer(app, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        previous_status = app.status
        app.status = Application.STATUS_UPDATING
        app.save(update_fields=["status", "updated_at"])

        for field, value in serializer.validated_data.items():
            setattr(app, field, value)

        try:
            update_deployment_in_k8s(app)
        except Exception:
            app.status = previous_status
            app.save(update_fields=["status", "updated_at"])
            raise

        app.status = Application.STATUS_ACTIVE
        app.save()
        return Response(ApplicationSerializer(app).data)

    def delete(self, request, pk):
        with transaction.atomic():
            app = get_object_or_404(
                Application.objects.select_for_update().select_related(
                    "namespace", "namespace__cluster"
                ),
                pk=pk,
            )
            if app.status == Application.STATUS_DELETING:
                raise ApplicationOperationInProgressError()
            app.status = Application.STATUS_DELETING
            app.save(update_fields=["status", "updated_at"])

        try:
            delete_deployment_in_k8s(app)
        except Exception:
            app.status = Application.STATUS_ACTIVE
            app.save(update_fields=["status", "updated_at"])
            raise

        app.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
