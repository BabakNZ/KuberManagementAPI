# K8s Manager Backend

A Django + DRF backend for managing Kubernetes clusters, namespaces, and
apps (Deployments) through a REST API. Built to the spec: Cluster is
pure DB storage, Namespace/App operations talk to the real Kubernetes
API, and App status is always read live rather than cached.

## Project layout

```
config/          Django project settings, root urls, wsgi/asgi
core/             Shared infrastructure: encryption, dynamic k8s client,
                  domain exceptions -> HTTP status mapping, log redaction
clusters/         Cluster model + API (pure DB, POST/GET)
namespaces/       Namespace model + API + Kubernetes service layer
                  (POST/GET/DELETE, concurrency-safe delete)
workloads/        Application (Deployment) model + API + service layer
                  (POST/GET/PATCH/DELETE, live pod status)
```

Each domain app follows the same shape: `models.py` (desired state +
status), `services.py` (Kubernetes I/O, framework-agnostic),
`views.py` (thin HTTP layer), `serializers.py`, `urls.py`, `admin.py`.
This separation is what makes it easy to later reuse the service layer
from a Celery task, a management command, or a different transport.

## Quick start (local, sqlite)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Generate and paste a key into .env:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

## Quick start (Docker Compose, Postgres)

```bash
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
export FIELD_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
docker compose up --build
```

## API reference

### Clusters

`POST /api/clusters/` — persists a cluster row only, no Kubernetes contact.
```json
{"name": "cluster-1", "address": "95.43.54.43:6443", "token": "<bearer token>"}
```
Response (201) never includes the token.

`GET /api/clusters/` — list clusters (token never included).

### Namespaces

`POST /api/namespaces/` — creates the namespace in Kubernetes, then in DB.
```json
{"cluster_id": 1, "name": "new-ns"}
```
- `404 cluster_not_found` if the cluster id doesn't exist
- `409 namespace_already_exists` if it's already there (in k8s or in our DB)
- `502 cluster_unreachable` if the cluster's API server can't be reached
- `400` for an invalid (non RFC-1123) namespace name

`GET /api/namespaces/?cluster_id=1` — namespaces **this backend created**,
read from the database (source of truth), not live from Kubernetes.

`DELETE /api/namespaces/<id>/` — concurrency-safe delete. A namespace
row is locked and flipped to a `deleting` status before any network
call; a second concurrent DELETE gets `409
namespace_operation_in_progress` immediately. Deleting an
already-gone-from-Kubernetes namespace still succeeds (idempotent).

### Apps

`POST /api/apps/` — creates a Deployment in the given namespace.
```json
{
  "namespace_id": 3,
  "name": "my-app",
  "image": "nginx:1.27",
  "replicas": 2,
  "cpu_request": "100m",
  "cpu_limit": "500m",
  "memory_request": "128Mi",
  "memory_limit": "512Mi"
}
```

`GET /api/apps/?namespace_id=3` — desired-state records plus a `live`
block per app, populated from Kubernetes at request time:
```json
{
  "id": 1, "name": "my-app", "namespace": 3, "replicas": 2,
  "status": "active",
  "live": {
    "ready": false,
    "ready_replicas": 1,
    "desired_replicas": 2,
    "pods": [
      {"name": "my-app-abc123", "phase": "Running", "ready": true},
      {"name": "my-app-def456", "phase": "Pending", "ready": false}
    ]
  }
}
```

`PATCH /api/apps/<id>/` — update `replicas`, `image`, or resource
requests/limits; patches the Deployment in Kubernetes.

`DELETE /api/apps/<id>/` — same concurrency-safe pattern as namespaces.

## Design notes / edge cases handled

- **Token security**: encrypted at rest (Fernet), write-only in the
  create serializer, excluded from every list/detail serializer and
  from the Django admin, and redacted from logs.
- **Namespace/App create**: Kubernetes is called first; if the
  subsequent DB write fails, a compensating delete is attempted against
  Kubernetes so nothing is orphaned. If the compensating delete also
  fails, this is logged loudly for manual/automated reconciliation.
- **Concurrent deletes**: `select_for_update()` inside a short
  transaction transitions `active -> deleting` before any network call,
  so a second simultaneous DELETE sees `deleting` and returns 409
  without ever reaching Kubernetes.
- **Crash between Kubernetes delete and DB delete**: the row is left in
  `deleting`. This repo doesn't ship a reconciliation job (out of scope
  per the assignment), but the service layer (`namespace_exists_in_k8s`)
  provides exactly what such a job would need — see the docstring in
  `namespaces/services.py`.
- **Idempotent deletes**: deleting something already gone from
  Kubernetes (404) is treated as success.
- **Live status**: `workloads/services.get_live_status` always queries
  Pods by label selector at request time; nothing about Pod/Deployment
  readiness is ever read from or written to the database.
- **Throttling**: DRF `ScopedRateThrottle` on all write endpoints
  (`cluster-write`, `namespace-write`, `app-write`), configurable via
  `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` in `config/settings.py`.

## Scaling this later

- Swap sqlite for Postgres via `DATABASE_URL` (already wired) — this is
  what lets you run multiple backend replicas behind a Service/Ingress.
- The Dockerfile runs `gunicorn` with multiple workers; scale further by
  running more Pod replicas of the same image in k3s.
- The Kubernetes client is built per-request from a `Cluster` row (see
  `core/k8s_client.py`) rather than from a static kubeconfig file, so
  adding a second, third, ... cluster is just another `POST
  /api/clusters/` call — no redeploy needed.
- Not yet implemented, worth adding when you need it: API
  authentication (currently open — add DRF `TokenAuthentication` or a
  JWT scheme before exposing this beyond localhost/your own network), a
  periodic reconciliation job (Celery beat or a k3s CronJob) for the
  `deleting`/orphan edge cases described above, and a real secrets
  backend for `FIELD_ENCRYPTION_KEY` instead of a plain env var.

## Next steps you mentioned

- **UI**: this API is CORS-enabled (`CORS_ALLOWED_ORIGINS` in `.env`) so
  a separate frontend (React/Vue/etc.) can call it directly. Happy to
  scaffold that next.
- **Connecting to your k3s cluster**: `POST /api/clusters/` with your
  k3s API server address (e.g. `<node-ip>:6443`) and a bearer token
  (e.g. from a ServiceAccount you create in the cluster with the RBAC
  permissions this backend needs — namespace and deployment/pod
  read/write). I can walk through generating that token and the
  matching ClusterRole/ClusterRoleBinding when you're ready.
