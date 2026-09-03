from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from core.metrics_view import metrics

def health(request):
    return JsonResponse({"status": "ok"})


def dashboard(request):
    return render(request, "dashboard.html")


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/clusters/", include("clusters.urls")),
    path("api/namespaces/", include("namespaces.urls")),
    path("api/apps/", include("workloads.urls")),
    path("api/backups/", include("backups.urls")),
    path("metrics", metrics),
]
