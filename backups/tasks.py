import gzip
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from celery import shared_task
from django.conf import settings
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from core.metrics import (
    backup_jobs_total,
    backup_duration_seconds,
    backups_in_progress,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def create_backup(self):
    backups_in_progress.inc()
    try:
        with backup_duration_seconds.time():
            """Create a compressed backup of the configured database.

            PostgreSQL is dumped with `pg_dump`; SQLite is copied directly. The
            task writes the compressed result into `settings.BACKUPS_DIR`."""
            db_settings = settings.DATABASES.get("default", {})
            engine = db_settings.get("ENGINE", "")
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
            extension = "sql.gz" if engine.endswith("postgresql") else "db.gz"
            out_name = f"backup-{timestamp}.{extension}"
            out_path = Path(settings.BACKUPS_DIR) / out_name

            if engine.endswith("postgresql"):
                logger.info("Creating PostgreSQL backup -> %s", out_path)
                pg_dump_env = os.environ.copy()
                if db_settings.get("PASSWORD"):
                    pg_dump_env["PGPASSWORD"] = str(db_settings["PASSWORD"])
                command = [
                    "pg_dump",
                    "--no-password",
                    "--format=plain",
                    "--host", str(db_settings.get("HOST") or "localhost"),
                    "--port", str(db_settings.get("PORT") or 5432),
                    "--username", str(db_settings.get("USER") or ""),
                    str(db_settings.get("NAME") or ""),
                ]
                with gzip.open(out_path, "wb") as dst:
                    subprocess.run(
                        command,
                        env=pg_dump_env,
                        stdout=dst,
                        check=True,
                        stderr=subprocess.PIPE,
                    )
            else:
                db_name = db_settings.get("NAME")
                if not db_name:
                    raise RuntimeError("Database NAME not configured; cannot create backup")

                db_path = Path(db_name)
                if not db_path.exists():
                    db_path = Path(settings.BASE_DIR) / db_path
                if not db_path.exists():
                    raise RuntimeError(f"Database file not found: {db_path}")

                logger.info("Creating SQLite backup for %s -> %s", db_path, out_path)
                with open(db_path, "rb") as src, gzip.open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            size = out_path.stat().st_size
            logger.info("Backup created: %s (%d bytes)", out_path, size)
            result = {"path": str(out_path), "size": size}

            # Optionally upload to S3 when bucket is configured
            s3_bucket = getattr(settings, "AWS_S3_BUCKET", None)
            if not s3_bucket and getattr(settings, "BACKUP_REMOTE_REQUIRED", False):
                raise RuntimeError(
                    "AWS_S3_BUCKET must be configured for durable production backups"
                )
            if s3_bucket:
                s3_key_prefix = getattr(settings, "AWS_S3_KEY_PREFIX", "") or ""
                s3_region = getattr(settings, "AWS_S3_REGION", None)
                s3_key = f"{s3_key_prefix}{out_name}" if s3_key_prefix else out_name
                try:
                    s3 = boto3.client("s3", region_name=s3_region)
                    s3.upload_file(str(out_path), s3_bucket, s3_key)
                    s3_url = f"s3://{s3_bucket}/{s3_key}"
                    logger.info("Uploaded backup to %s", s3_url)
                    result["s3_url"] = s3_url
                except (BotoCoreError, ClientError) as exc:  # pragma: no cover - external
                    logger.exception("Failed to upload backup to S3: %s", exc)
                    raise RuntimeError("Backup upload to S3 failed") from exc

            backup_jobs_total.labels(
                outcome="completed"
            ).inc()

            return result
    except Exception:
        backup_jobs_total.labels(
            outcome="failed"
        ).inc()

        raise
    finally:
        backups_in_progress.dec()
