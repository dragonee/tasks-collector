"""Thin boto3 wrapper for trip-photo object storage.

Two endpoints are in play (see settings): the *in-network* endpoint the
backend/worker use to read and write objects, and the *public* endpoint
baked into presigned URLs handed to the device. In production both are
``None`` (real AWS); in dev they differ (``tasks-minio`` vs a
device-reachable host).

This module is deliberately tiny — it is the seam that tests monkeypatch
to avoid talking to a real bucket.
"""

from django.conf import settings

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def _config():
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": settings.AWS_S3_ADDRESSING_STYLE},
    )


def _client(endpoint_url):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,
        region_name=settings.AWS_S3_REGION_NAME,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=_config(),
    )


def _internal_client():
    return _client(settings.AWS_S3_ENDPOINT_URL)


def _public_client():
    return _client(settings.AWS_S3_PUBLIC_ENDPOINT_URL)


def presign_put(key, content_type, expires=None):
    """Presigned PUT URL the client uses to upload the original directly."""
    expires = expires if expires is not None else settings.PHOTO_PRESIGN_PUT_TTL
    return _public_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
    )


def presign_get(key, expires=None):
    """Short-lived presigned GET URL for displaying an object."""
    expires = expires if expires is not None else settings.PHOTO_PRESIGN_GET_TTL
    return _public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def object_exists(key):
    """True if the object exists in the bucket."""
    try:
        _internal_client().head_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def download_bytes(key):
    obj = _internal_client().get_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
    return obj["Body"].read()


def upload_bytes(key, data, content_type):
    _internal_client().put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
