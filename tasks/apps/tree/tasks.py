import io

from django.conf import settings

from celery import shared_task
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

# Teach Pillow to decode the HEIC/HEIF originals phones upload by default.
register_heif_opener()


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def generate_photo_thumbnail(self, photo_added_id):
    """Generate a WebP thumbnail for a PhotoAdded original and record its key.

    Idempotent: a no-op once ``thumbnail_key`` is set. Retried on transient
    failures (e.g. the original not yet visible in the bucket).
    """
    from .models import PhotoAdded
    from .services.photos import storage, thumbnail_key_for

    try:
        photo = PhotoAdded.objects.get(pk=photo_added_id)
    except PhotoAdded.DoesNotExist:
        return
    if photo.thumbnail_key:
        return

    try:
        raw = storage.download_bytes(photo.original_key)
    except Exception as exc:  # noqa: BLE001 - retry any storage hiccup
        raise self.retry(exc=exc)

    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    max_edge = settings.PHOTO_THUMBNAIL_MAX_EDGE
    img.thumbnail((max_edge, max_edge))
    img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=80)

    tkey = thumbnail_key_for(photo.original_key)
    storage.upload_bytes(tkey, buf.getvalue(), "image/webp")

    PhotoAdded.objects.filter(pk=photo.pk).update(
        thumbnail_key=tkey, width=img.width, height=img.height
    )
