"""檔案儲存。依 STORAGE_BACKEND 選 S3 或本機檔案:

storage = get_storage()
mime = validate_upload(data, IMAGE_TYPES, config.storage_max_upload_mb * 1024 * 1024)
key = new_object_key("avatars", mime)
storage.put(key, data, mime)
url = storage.presigned_url(key)
"""

from functools import cache

from app.common.core.config import config
from app.common.storage.external_services import LocalStorage, S3Storage, Storage


@cache
def get_storage() -> Storage:
    if config.storage_backend == "s3":
        return S3Storage(config.s3_bucket, config.aws_region, config.aws_access_key_id, config.aws_secret_access_key)
    return LocalStorage(config.storage_local_dir)
