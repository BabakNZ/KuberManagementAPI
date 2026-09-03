from django.http import HttpResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)


def metrics(request):
    registry = CollectorRegistry()

    multiprocess.MultiProcessCollector(registry)

    return HttpResponse(
        generate_latest(registry),
        content_type=CONTENT_TYPE_LATEST,
    )