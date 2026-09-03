from prometheus_client import Counter, Gauge, Histogram


kubernetes_operations_total = Counter(
    "hamamooz_kubernetes_operations_total",
    "Total number of Kubernetes operations by resource, operation and outcome",
    ["resource", "operation", "outcome"],
)

kubernetes_operation_duration_seconds = Histogram(
    "hamamooz_kubernetes_operation_duration_seconds",
    "Duration of Kubernetes operations in seconds",
    ["resource", "operation"],
)

backup_jobs_total = Counter(
    "hamamooz_backup_jobs_total",
    "Total number of backup jobs by terminal outcome",
    ["outcome"],
)

backup_duration_seconds = Histogram(
    "hamamooz_backup_duration_seconds",
    "Duration of backup work in seconds",
)

backups_in_progress = Gauge(
    "hamamooz_backups_in_progress",
    "Number of backup jobs currently in progress",
    multiprocess_mode="livesum",
)