"""檔案儲存:magic bytes、大小上限、本機 backend、S3 presign 快取(本地簽章,不連網)。"""

import pytest
from botocore.stub import Stubber

from app.common.exceptions import NotFoundException, ValidationException
from app.common.storage.external_services import LocalStorage, S3Storage
from app.common.storage.utils import IMAGE_TYPES, new_object_key, sniff_mime, validate_upload

pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"GIF89a....", "image/gif"),
        (b"\x00\x00\x00\x18ftypheic", "image/heic"),
        (b"%PDF-1.7", "application/pdf"),
        (b"<html>", None),
    ],
)
def test_sniff_mime(data, mime):
    assert sniff_mime(data) == mime


def test_validate_upload_rejects_too_large_and_wrong_type():
    assert validate_upload(PNG, IMAGE_TYPES, 1024) == "image/png"
    with pytest.raises(ValidationException) as too_large:
        validate_upload(PNG, IMAGE_TYPES, 4)
    assert too_large.value.reason == "file_too_large"
    with pytest.raises(ValidationException) as wrong:
        validate_upload(b"%PDF-1.7", IMAGE_TYPES, 1024)  # 副檔名改成 .png 也騙不過檔頭
    assert wrong.value.reason == "unsupported_file_type"


def test_new_object_key_ignores_user_filename():
    key = new_object_key("/avatars/", "image/png")

    assert key.startswith("avatars/") and key.endswith(".png")


def test_local_storage_roundtrip(tmp_path):
    storage = LocalStorage(str(tmp_path))

    storage.put("a/b.png", PNG, "image/png")

    assert storage.get("a/b.png") == PNG
    assert storage.presigned_url("a/b.png") == "/media/a/b.png"
    storage.delete("a/b.png")
    with pytest.raises(NotFoundException):
        storage.get("a/b.png")


def test_local_storage_blocks_path_traversal(tmp_path):
    with pytest.raises(NotFoundException):
        LocalStorage(str(tmp_path / "media")).get("../secret.txt")


@pytest.fixture()
def s3():
    return S3Storage("demo-bucket", "ap-northeast-1", "AKIAEXAMPLEEXAMPLE00", "example-secret-not-real")


def test_presigned_url_uses_regional_virtual_host_and_is_cached(s3):
    url = s3.presigned_url("a.png")

    assert url.startswith("https://demo-bucket.s3.ap-northeast-1.amazonaws.com/a.png?")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert s3.presigned_url("a.png") == url  # 同一時段回同一個網址,瀏覽器可快取


def test_s3_errors_become_external_api_exception(s3):
    from app.common.exceptions import ExternalAPIException

    with Stubber(s3._client) as stub:
        stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        with pytest.raises(ExternalAPIException):
            s3.get("missing.png")


def test_s3_put(s3):
    with Stubber(s3._client) as stub:
        stub.add_response(
            "put_object", {}, {"Bucket": "demo-bucket", "Key": "a.png", "Body": PNG, "ContentType": "image/png"}
        )
        s3.put("a.png", PNG, "image/png")
        stub.assert_no_pending_responses()
