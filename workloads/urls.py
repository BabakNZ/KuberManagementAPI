from django.urls import path

from .views import ApplicationDetailView, ApplicationListCreateView

urlpatterns = [
    path("", ApplicationListCreateView.as_view(), name="application-list-create"),
    path("<int:pk>/", ApplicationDetailView.as_view(), name="application-detail"),
]
