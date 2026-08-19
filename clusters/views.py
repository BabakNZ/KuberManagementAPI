from rest_framework import generics, status
from rest_framework.response import Response

from .models import Cluster
from .serializers import ClusterCreateSerializer, ClusterListSerializer


class ClusterListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/clusters/  -> list clusters (never includes token)
    POST /api/clusters/  -> persist a cluster row ONLY (no k8s contact)
    """

    queryset = Cluster.objects.all()
    throttle_scope = "cluster-write"

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClusterCreateSerializer
        return ClusterListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cluster = serializer.save()
        # Respond with the safe (list) representation, not the create
        # serializer's, so the token can never round-trip in the response
        # even though it's write_only (defense in depth).
        return Response(
            ClusterListSerializer(cluster).data, status=status.HTTP_201_CREATED
        )
