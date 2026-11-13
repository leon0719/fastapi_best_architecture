"""檔案儲存:S3(正式環境)與本機檔案(本機開發)。boto3 只能在這個檔案 import 與呼叫。"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger

from app.common.exceptions import ExternalAPIException, NotFoundException

PRESIGN_EXPIRES_IN = 3600
# 同一個 key 在 50 分鐘區間內回同一個網址(瀏覽器可快取圖片),每個網址至少還有 10 分鐘有效
PRESIGN_BUCKET_SECONDS = 3000


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def presigned_url(self, key: str) -> str: ...


@contextmanager
def _wrap_errors(action: str, key: str) -> Iterator[None]:
    """SDK 錯誤統一轉成 ExternalAPIException(502);log 帶 key 與耗時,不帶金鑰。"""
    start = time.monotonic()
    try:
        yield
    except (BotoCoreError, ClientError) as e:
        logger.exception(f"[External] S3 {action} failed - key: {key}, duration: {time.monotonic() - start:.3f}s")
        raise ExternalAPIException("檔案儲存服務暫時無法使用,請稍後再試") from e


class S3Storage:
    """金鑰留空時交給 boto3 預設憑證鏈(EC2 instance role 等),正式環境建議不存 key。"""

    def __init__(self, bucket: str, region: str, access_key_id: str = "", secret_access_key: str = "") -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            # presigned URL 用 SigV4;virtual 定址才會產生區域端點 <bucket>.s3.<region>.amazonaws.com。
            # 預設的全域端點對新 bucket 會回 307 轉址到區域端點,瀏覽器跟過去後 host 不符、簽章失效。
            config=BotoConfig(
                signature_version="s3v4", s3={"addressing_style": "virtual"}, retries={"mode": "standard"}
            ),
        )
        self._sign = lru_cache(maxsize=1024)(self._sign_uncached)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        with _wrap_errors("put", key):
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        logger.info(f"[External] S3 put - key: {key}, size: {len(data)}")

    def get(self, key: str) -> bytes:
        with _wrap_errors("get", key):
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        with _wrap_errors("delete", key):
            self._client.delete_object(Bucket=self._bucket, Key=key)

    def presigned_url(self, key: str) -> str:
        """本地簽章,不連網。依時段快取,同一個 key 在同一時段回同一個網址。"""
        return self._sign(key, int(time.time() // PRESIGN_BUCKET_SECONDS))

    def _sign_uncached(self, key: str, _time_bucket: int) -> str:
        with _wrap_errors("presign", key):
            return self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=PRESIGN_EXPIRES_IN
            )


class LocalStorage:
    """本機開發用:存在 STORAGE_LOCAL_DIR,DEBUG 時由 /media 提供下載(見 app/main.py)。"""

    def __init__(self, root: str, base_url: str = "/media") -> None:
        self._root = Path(root).resolve()
        self._base_url = base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):  # 擋 ../ 路徑穿越
            raise NotFoundException("File not found")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info(f"[External] Local storage put - key: {key}, size: {len(data)}")

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundException("File not found")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def presigned_url(self, key: str) -> str:
        self._path(key)
        return f"{self._base_url}/{key}"
