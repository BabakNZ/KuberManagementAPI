from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/clusters/", include("clusters.urls")),
    path("api/namespaces/", include("namespaces.urls")),
    path("api/apps/", include("workloads.urls")),
]
