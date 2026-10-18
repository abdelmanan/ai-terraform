import logging

from backend.config import settings

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

except ImportError:
    boto3 = None
    BotoCoreError = ClientError = ()


class StorageError(Exception):
    """Raised when a built archive could not be published for download."""


def is_remote():
    return bool(settings.S3_BUCKET)


def publish_archive(zip_path, generation_id, project_name):
    """Return the URL the browser must call to download `zip_path`."""

    if not is_remote():
        return f"/api/download/{generation_id}"

    if boto3 is None:
        raise StorageError("S3_BUCKET is set but boto3 is not installed.")

    key = f"{settings.S3_PREFIX.strip('/')}/{generation_id}/{project_name}.zip"

    client = boto3.client("s3", region_name=settings.AWS_REGION)

    try:
        client.upload_file(
            zip_path,
            settings.S3_BUCKET,
            key,
            ExtraArgs={"ContentType": "application/zip"}
        )

        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{project_name}.zip"'
            },
            ExpiresIn=settings.DOWNLOAD_URL_TTL_SECONDS
        )

    except (BotoCoreError, ClientError) as exc:
        raise StorageError(f"Could not upload the archive to S3: {exc}")

    logger.info(
        "Archive for '%s' uploaded to s3://%s/%s",
        project_name, settings.S3_BUCKET, key
    )

    return url
