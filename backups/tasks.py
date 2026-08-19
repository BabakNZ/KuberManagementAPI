import gzip
import logging
import shutil
from datetime import datetime
from pathlib import Path

from celery import shared_task
from django.conf import settings
import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def create_backup(self):
    """Create a compressed backup of the sqlite database file.

    The task writes a gzipped copy into `settings.BACKUPS_DIR` and returns
    the saved file path.
    """
    db_settings = settings.DATABASES.get("default", {})
    db_name = db_settings.get("NAME")
    if not db_name:
        raise RuntimeError("Database NAME not configured; cannot create backup")

    db_path = Path(db_name)
    if not db_path.exists():
        # Try relative to project base
        db_path = Path(settings.BASE_DIR) / db_path
    if not db_path.exists():
        raise RuntimeError(f"Database file not found: {db_path}")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_name = f"backup-{timestamp}.db.gz"
    out_path = Path(settings.BACKUPS_DIR) / out_name

    logger.info("Creating backup for %s -> %s", db_path, out_path)

    # Copy and compress
    with open(db_path, "rb") as src, gzip.open(out_path, "wb") as dst:
        shutil.copyfileobj(src, dst)

    size = out_path.stat().st_size
    logger.info("Backup created: %s (%d bytes)", out_path, size)
    result = {"path": str(out_path), "size": size}

    # Optionally upload to S3 when bucket is configured
    s3_bucket = getattr(settings, "AWS_S3_BUCKET", None)
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
            result["s3_error"] = str(exc)

    return result
