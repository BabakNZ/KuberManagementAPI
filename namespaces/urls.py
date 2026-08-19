from django.urls import path

from .views import NamespaceDetailView, NamespaceListCreateView

urlpatterns = [
    path("", NamespaceListCreateView.as_view(), name="namespace-list-create"),
    path("<int:pk>/", NamespaceDetailView.as_view(), name="namespace-detail"),
]
