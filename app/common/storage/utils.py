"""上傳檔案檢查:以 magic bytes 判斷 MIME(不信任副檔名與 Content-Type)、大小上限、物件 key。"""

import uuid
from datetime import UTC, datetime

from app.common.exceptions import ErrorCode, ValidationException

_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}

EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/heic": "heic",
    "application/pdf": "pdf",
}
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic"})


def sniff_mime(data: bytes) -> str | None:
    """從檔頭判斷格式;認不出來回 None。HEIC 與 HEIF 是同一種容器,一律回 image/heic。"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def validate_upload(data: bytes, allowed: frozenset[str], max_bytes: int) -> str:
    """回傳偵測到的 MIME;太大或格式不允許 → ValidationException(400,帶各自的 reason)。"""
    if len(data) > max_bytes:
        raise ValidationException(f"檔案大小超過上限 {max_bytes // (1024 * 1024)} MB", reason=ErrorCode.FILE_TOO_LARGE)
    mime = sniff_mime(data)
    if mime is None or mime not in allowed:
        raise ValidationException("不支援的檔案格式", reason=ErrorCode.UNSUPPORTED_FILE_TYPE)
    return mime


def new_object_key(prefix: str, mime: str, now: datetime | None = None) -> str:
    """<prefix>/<YYYY>/<MM>/<uuid>.<ext>:不用使用者給的檔名(路徑穿越、重名、個資)。"""
    now = now or datetime.now(UTC)
    return f"{prefix.strip('/')}/{now:%Y/%m}/{uuid.uuid4().hex}.{EXTENSIONS.get(mime, 'bin')}"
