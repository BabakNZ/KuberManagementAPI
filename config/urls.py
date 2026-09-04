from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from core.metrics_view import metrics

def health(request):
    return JsonResponse({"status": "ok"})


def readiness(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "not_ready"}, status=503)
    return JsonResponse({"status": "ready"})


def dashboard(request):
    return render(request, "dashboard.html")


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/health/ready/", readiness, name="readiness"),
    path("api/clusters/", include("clusters.urls")),
    path("api/namespaces/", include("namespaces.urls")),
    path("api/apps/", include("workloads.urls")),
    path("api/backups/", include("backups.urls")),
    path("metrics", metrics),
]
