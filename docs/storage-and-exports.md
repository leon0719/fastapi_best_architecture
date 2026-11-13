# 檔案儲存與匯出

## 儲存(`app/common/storage/`)

```python
from app.common.storage import get_storage
from app.common.storage.utils import IMAGE_TYPES, new_object_key, validate_upload

data = await file.read()
mime = validate_upload(
    data, IMAGE_TYPES, config.storage_max_upload_mb * 1024 * 1024
)  # 400 file_too_large / unsupported_file_type
key = new_object_key("avatars", mime)  # avatars/2026/11/<uuid>.png,不用使用者給的檔名
get_storage().put(key, data, mime)
url = get_storage().presigned_url(key)
```

- MIME 以檔頭 magic bytes 判斷,不信任副檔名與 Content-Type。
- `STORAGE_BACKEND=s3`:boto3、SigV4、virtual-hosted 區域端點(避免 307 轉址讓簽章失效);presigned URL 每 50 分鐘一個時段
  內回同一個網址(瀏覽器能快取),每個網址至少還有 10 分鐘有效。金鑰留空 → instance role。
- `STORAGE_BACKEND=local`(本機開發):存 `STORAGE_LOCAL_DIR`,`DEBUG=True` 時由 `/media/<key>` 提供下載;正式環境不要用。
- S3 錯誤轉成 `ExternalAPIException`(502)。nginx 的 `client_max_body_size` 要略大於 `STORAGE_MAX_UPLOAD_MB`。

## 匯出(`app/common/exports.py`)

```python
headers, rows = service.export_rows()
return table_export_response(format, "使用者清單", headers, rows, basename="使用者清單_20261113")  # xlsx / pdf / zip
```

或分開用 `build_xlsx`(標題列樣式、凍結、欄寬依中文寬度估算、公式注入防護)、`build_pdf_table`(中文字型、跨頁重複表頭)、
`build_zip` 與 `file_response(data, filename, media_type)`。範例:`GET /api/v1/users/export?format=xlsx|pdf|zip`。

- 下載回應用 `StreamingResponse`,`Content-Disposition` 同時給 ASCII `filename` 與 RFC 5987 `filename*=UTF-8''…`(中文檔名),
  `Cache-Control: no-store`。CORS 已 expose `Content-Disposition`。
- 下載端點不包 `BaseResponse`(回的是檔案);錯誤仍然 raise,照常變成 BaseResponse。
- 中文 PDF 嵌入 TrueType 字型 `fonts-arphic-uming`(Dockerfile 安裝,`PDF_FONT_PATH` 可改)。reportlab 不支援 Noto Sans CJK
  的 CFF 外框;找不到字型(macOS 本機)時退回不嵌入的 CID 字型,部分閱讀器會缺字,正式環境務必有字型檔。
- 大量資料:改用長任務產檔、存到 storage,完成後給 presigned URL,不要在請求內產幾十 MB 的檔案。
