"""Avatar upload endpoints.

POST /api/avatar/upload-url  -> {uploadUrl, key}
POST /api/avatar/confirm     -> records the uploaded object as the user's avatar
"""
import re

from lib import db, storage
from lib.auth import current_user
from lib.http import error

BUCKET = "pn-user-media"
KEY_PREFIX = "avatars/orig/"
MAX_BYTES = 5 * 1024 * 1024
URL_TTL_SECONDS = 60


def safe_name(filename: str) -> str:
    name = re.split(r"[\\/]", filename)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lower()
    return name[:100] or "avatar"


def create_upload_url(request):
    user = current_user(request)
    body = request.json()
    content_type = str(body["contentType"])
    size = int(body["size"])

    if not content_type.startswith("image/"):
        return error(400, "unsupported_type")
    if size > MAX_BYTES:
        return error(413, "too_large")

    key = KEY_PREFIX + safe_name(str(body["filename"]))
    url = storage.presign_put(
        BUCKET, key, content_type=content_type, expires_in=URL_TTL_SECONDS
    )
    return {"uploadUrl": url, "key": key}


def confirm(request):
    user = current_user(request)
    key = str(request.json()["key"])

    if not key.startswith(KEY_PREFIX) or not storage.exists(BUCKET, key):
        return error(400, "unknown_object")

    previous = db.users.get_avatar_key(user.id)
    db.users.set_avatar_key(user.id, key)
    if previous:
        storage.delete_many(BUCKET, avatar_objects(previous))
    return {"key": key}


def avatar_objects(key: str) -> list[str]:
    name = key[len(KEY_PREFIX):]
    return [key, f"avatars/thumb/128/{name}", f"avatars/thumb/512/{name}"]
