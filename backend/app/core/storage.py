"""Private local/S3 object storage. Only the authenticated API serves objects."""
from functools import lru_cache
from pathlib import Path
from app.core.config import settings


@lru_cache
def s3_client():
    import boto3
    return boto3.client("s3", endpoint_url=settings.s3_endpoint_url,
                        aws_access_key_id=settings.s3_access_key_id,
                        aws_secret_access_key=settings.s3_secret_access_key,
                        region_name=settings.s3_region)


def local_path(value: str) -> Path:
    root = (settings.artifacts_dir / "uploads").resolve()
    path = Path(value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Upload path outside storage root")
    return path


def put(key: str, data: bytes) -> str:
    if settings.storage_backend == "s3":
        s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data,
                               ContentType="application/octet-stream")
        return f"s3://{key}"
    path = local_path(str(settings.artifacts_dir / "uploads" / key))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def read(value: str):
    if value.startswith("s3://"):
        return s3_client().get_object(Bucket=settings.s3_bucket, Key=value[5:])["Body"]
    return local_path(value).open("rb")


def remove(value: str):
    if value.startswith("s3://"):
        s3_client().delete_object(Bucket=settings.s3_bucket, Key=value[5:])
    else:
        local_path(value).unlink(missing_ok=True)
