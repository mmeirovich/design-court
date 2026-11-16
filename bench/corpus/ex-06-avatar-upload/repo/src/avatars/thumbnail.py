"""Object-created handler: writes square JPEG thumbnails for an uploaded avatar."""
from io import BytesIO
from urllib.parse import unquote_plus

from PIL import Image, ImageOps

from lib import storage

SIZES = (128, 512)
OUT_PREFIX = "avatars/thumb/"


def handler(event, context):
    for record in event["records"]:
        bucket = record["bucket"]
        key = unquote_plus(record["key"])
        name = key.rsplit("/", 1)[-1]

        data = storage.get_object(bucket, key)
        image = Image.open(BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")

        for size in SIZES:
            thumb = ImageOps.fit(image, (size, size), Image.LANCZOS)
            out = BytesIO()
            thumb.save(out, "JPEG", quality=85)
            storage.put_object(
                bucket,
                f"{OUT_PREFIX}{size}/{name}",
                out.getvalue(),
                content_type="image/jpeg",
            )
