from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from celery.result import AsyncResult

from .tasks import create_backup
from config import celery_app


class BackupCreateView(APIView):
    """Trigger a backup task via Celery and return the task id."""

    def post(self, request, *args, **kwargs):
        async_result = create_backup.apply_async()
        return Response({"task_id": async_result.id}, status=status.HTTP_202_ACCEPTED)


class BackupStatusView(APIView):
    """Return Celery task status/result for a given task id."""

    def get(self, request, task_id, *args, **kwargs):
        res = AsyncResult(task_id, app=celery_app)
        data = {"task_id": task_id, "status": res.status}
        if res.ready():
            try:
                data["result"] = res.result
            except Exception as exc:  # pragma: no cover - defensive
                data["result_error"] = str(exc)
        return Response(data)
