"""AWS S3 storage for successful crawl results."""

from pathlib import Path

import boto3

from . import config


def upload_result(file_path: str, run_id: str) -> str | None:
    """
    Upload a crawl JSON result to S3.

    Returns the S3 URI when successful.
    Returns None when S3 storage is disabled.

    Uses boto3's default credential provider chain.
    Credentials are never hardcoded here.
    """

    if not config.S3_ENABLED:
        return None

    if not config.S3_BUCKET:
        raise ValueError("S3 is enabled but S3_BUCKET is not configured.")

    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Crawl result not found: {path}")

    s3 = boto3.client(
        "s3",
        region_name=config.AWS_REGION,
    )

    key = f"crawl-results/{run_id}.json"

    s3.upload_file(
        str(path),
        config.S3_BUCKET,
        key,
        ExtraArgs={
            "ContentType": "application/json",
            "ServerSideEncryption": "AES256",
        },
    )

    return f"s3://{config.S3_BUCKET}/{key}"