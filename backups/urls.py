from django.urls import path

from .views import BackupCreateView, BackupStatusView

urlpatterns = [
    path("", BackupCreateView.as_view(), name="backup-create"),
    path("status/<str:task_id>/", BackupStatusView.as_view(), name="backup-status"),
]
