# K8s Manager

A Django REST API and React UI for registering Kubernetes clusters, creating
namespaces, and managing application Deployments. Cluster credentials are
encrypted at rest with Fernet. PostgreSQL stores control-plane records and
application status is read live from Kubernetes.

## Production boundary

The API does not provide user authentication. Do not expose it directly to
the public internet. Put it behind a private network, VPN, SSO proxy, or add
application authentication before public exposure. Configure TLS and
authentication for the Ingress controller used by your cluster.

## Project layout

```bash
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

## Local development (SQLite)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Generate and paste a key into .env:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

Run the UI in a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

The Vite server proxies `/api` to `http://127.0.0.1:8000`.

## Docker Compose

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, and POSTGRES_PASSWORD in .env.
docker compose up --build
```

Open `http://localhost:8080`. Compose runs PostgreSQL, Redis, the backend,
Celery worker, and the frontend. Database and Redis are internal services.

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

## Kubernetes deployment on a Linux VM

`deploy/k8s/` is a Kustomize baseline for k3s or Kubernetes on one Linux VM.
It includes PostgreSQL, Redis, two backend replicas, one Celery worker, two
frontend replicas, probes, a PVC, and an Ingress. For critical workloads,
prefer managed PostgreSQL/Redis and an external secret manager.

### Build and publish images

```bash
export REGISTRY=registry.example.com/team
export TAG=$(git rev-parse --short HEAD)
docker build -t "$REGISTRY/k8s-manager-backend:$TAG" .
docker build -t "$REGISTRY/k8s-manager-frontend:$TAG" ./frontend
docker push "$REGISTRY/k8s-manager-backend:$TAG"
docker push "$REGISTRY/k8s-manager-frontend:$TAG"
```

For a single-node k3s VM without a registry, import both images into the
node's container runtime and use the same image names in the manifests.

### Create secrets

Do not apply `deploy/k8s/secret.example.yaml` unchanged. Create the Secret
directly so credentials are not committed:

```bash
kubectl create namespace k8s-manager
kubectl -n k8s-manager create secret generic k8s-manager-secrets \
  --from-literal=DJANGO_SECRET_KEY='<long-random-value>' \
  --from-literal=FIELD_ENCRYPTION_KEY='<Fernet-key>' \
  --from-literal=POSTGRES_PASSWORD='<long-random-password>'
```

Edit `deploy/k8s/app.yaml` and set the hostname in its ConfigMap and Ingress.
Use the same HTTPS origin for `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS`.

### Apply and verify

```bash
kubectl -n k8s-manager apply -k deploy/k8s
kubectl -n k8s-manager set image deployment/backend \
  backend="$REGISTRY/k8s-manager-backend:$TAG"
kubectl -n k8s-manager set image deployment/worker \
  worker="$REGISTRY/k8s-manager-backend:$TAG"
kubectl -n k8s-manager set image deployment/frontend \
  frontend="$REGISTRY/k8s-manager-frontend:$TAG"
kubectl -n k8s-manager rollout status deployment/backend
kubectl -n k8s-manager rollout status deployment/frontend
kubectl -n k8s-manager get pods,svc,ingress,pvc
```

Each backend pod runs migrations in an init container before starting Gunicorn.
The frontend proxies `/api` to the internal backend Service, so the browser
uses one origin. Configure DNS and TLS for the Ingress controller.

## Production configuration

`DJANGO_DEBUG=False`, explicit `DJANGO_ALLOWED_HOSTS`, PostgreSQL via
`DATABASE_URL`, and `FIELD_ENCRYPTION_KEY` are required in production.
`K8S_VERIFY_SSL=True` should be used with a trusted CA. Changing the Fernet
key makes existing encrypted cluster tokens unreadable, so back it up with
the database credentials.

Health endpoints are `/api/health/` for liveness and
`/api/health/ready/` for database readiness. `/metrics` exposes Prometheus
metrics and should remain internal or be protected at the ingress.

## Backups / Celery

This project includes a simple backups API that enqueues backup tasks
to a Celery worker using Redis as the broker/result backend. The task
creates a gzipped copy of the sqlite DB under the `backups/` folder.

Run Redis (e.g. via Docker) and start a worker/server locally:

```bash
# start redis
docker run -p 6379:6379 --name redis -d redis:7

# install deps
pip install -r requirements.txt

# run Django dev server
python manage.py runserver

# start celery worker (from project root)
celery -A config worker -l info
```

Trigger a backup via HTTP:

```bash
curl -X POST http://localhost:8000/api/backups/
```

The endpoint returns a Celery task id. The worker will create a file
like `backups/backup-20260819T123456Z.db.gz` when complete.

### Docker Compose + S3

The included `docker-compose.yml` now provides `redis` and a `worker`
service (Celery) alongside the `backend`. To run everything together:

```bash
export DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))")
export FIELD_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# optional: set S3 upload vars
export AWS_S3_BUCKET=your-bucket
export AWS_S3_REGION=us-east-1
export AWS_S3_KEY_PREFIX=backups/

docker compose up --build
```

When `AWS_S3_BUCKET` is set, backups will be uploaded to S3 and the
task result will include an `s3_url` like `s3://your-bucket/backups/backup-...`.
