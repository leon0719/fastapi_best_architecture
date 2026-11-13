import os
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# ENV 決定要載入哪個 .env 檔:local -> .env.local, prod -> .env.prod。
# 未設定時預設 local,所以本地開發不用特別 export;Docker compose 用 env_file
# 明確指定該環境的檔案,process 環境不會有 ENV,故仍以此變數的預設值為準。
_env = os.environ.get("ENV", "local")
_env_file = f".env.{_env}"

_PLACEHOLDER_MARKERS = ("changeme", "your-", "change-in-production", "<")  # "<": .env.prod.example 的 <...>

# 開發用的預設值:本機方便,上線就是弱密碼。
_INSECURE_DEFAULTS = frozenset({"postgres", "redis_password", "admin123", "admin", "password", "secret", ""})

# admin_secret_key 是 SessionMiddleware 的簽章金鑰,太短等於可暴力破解。
_MIN_SECRET_LENGTH = 32


def _looks_unset(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in _INSECURE_DEFAULTS or any(m in lowered for m in _PLACEHOLDER_MARKERS)


class Config(BaseSettings):
    """Application settings, bound to environment variables by pydantic-settings.

    Field names map to env vars case-insensitively (db_host <- DB_HOST).
    Values in the real environment override those in .env.
    機密欄位一律 repr=False:例外訊息、log、Sentry 把 Config 印出來時不會帶出金鑰。

    選用功能(Google 登入、S3、SMTP、LINE、LLM、Sentry)留空 = 不啟用;一旦啟用,
    它的機密欄位就會被 security_issues() 檢查。
    """

    model_config = SettingsConfigDict(env_file=_env_file, env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Best FastAPI Architecture"
    env: str = "local"
    debug: bool = False

    # Database configuration
    db_host: str = "db"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = Field(default="postgres", repr=False)
    db_name: str = "fastapi_db"

    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = Field(default="redis_password", repr=False)
    redis_db: int = 0
    redis_decode_responses: bool = True

    # Admin panel configuration (optional for migrations)
    admin_secret_key: str = Field(default="", repr=False)
    admin_username: str = ""
    admin_password: str = Field(default="", repr=False)

    # ---- 可觀測性 ----
    # Sentry:留空 = 不啟用(本機、測試)
    sentry_dsn: str = Field(default="", repr=False)
    sentry_traces_sample_rate: float = 0.0

    # ---- CORS / 前端 ----
    # 逗號分隔;前端用 Authorization: Bearer 帶 token,不開 allow_credentials
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    # Google 登入完成後導回的前端網址
    frontend_base_url: str = "http://localhost:5173"

    # ---- Rate limit(slowapi) ----
    rate_limit_enabled: bool = True
    # 留空 = 用上面的 Redis(多 worker 共用計數);memory:// 只適合單 worker 或測試
    rate_limit_storage_uri: str = Field(default="", repr=False)
    rate_limit_auth: str = "10/minute"  # 登入相關端點,依來源 IP

    # ---- Google 登入(OAuth 授權碼 + PKCE) ----
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = Field(default="", repr=False)
    # 只接受這個 Google Workspace 網域(ID token 的 hd);留空 = 不限網域(仍需 email_verified)
    google_allowed_domain: str = ""
    # True:第一次登入自動建立帳號(role=user);False:只有後台建好的帳號能登入
    google_auto_register: bool = False
    auth_session_ttl_days: int = 30

    # ---- 稽核 ----
    audit_retention_days: int = 365  # 0 = 永久保存

    # ---- 排程 / 長任務 ----
    scheduler_enabled: bool = True
    job_ttl_seconds: int = 24 * 3600

    # ---- 檔案儲存 ----
    storage_backend: str = "local"  # local | s3
    storage_local_dir: str = "media"
    storage_max_upload_mb: int = 10
    aws_region: str = "ap-northeast-1"
    # 留空 → boto3 預設憑證鏈(EC2 instance role 等),正式環境建議這樣做
    aws_access_key_id: str = Field(default="", repr=False)
    aws_secret_access_key: str = Field(default="", repr=False)
    s3_bucket: str = ""

    # ---- 匯出 ----
    # TrueType 外框的中文字型(reportlab 不支援 CFF/OTF);Dockerfile 安裝 fonts-arphic-uming
    pdf_font_path: str = "/usr/share/fonts/truetype/arphic/uming.ttc"
    pdf_font_subfont_index: int = 2  # uming.ttc:2 = UMing TW(繁體字形)

    # ---- 通知 ----
    smtp_host: str = ""  # 留空 = 不寄信,只寫 log
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_from_email: str = ""
    line_channel_access_token: str = Field(default="", repr=False)  # 留空 = 不推播,只寫 log
    line_channel_secret: str = Field(default="", repr=False)  # webhook 簽章驗證用;留空 = webhook 一律拒絕
    notification_max_retries: int = 5
    notification_retry_interval_seconds: int = 60
    notification_retention_days: int = 30  # 已送出/已放棄的 outbox 列保留天數;0 = 永久保存

    # ---- LLM(選用,需 `uv sync --extra llm`) ----
    # 依序嘗試,認證/額度錯誤時換下一家;留空 = 不啟用
    llm_providers: Annotated[list[str], NoDecode] = []
    anthropic_api_key: str = Field(default="", repr=False)
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-5-mini"
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"

    @field_validator("cors_origins", "llm_providers", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("frontend_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def db_url(self) -> str:
        """PostgreSQL database URL"""
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        """Redis connection URL"""
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    def security_issues(self) -> list[str]:
        """列出「不該帶上線」的設定值。debug 環境用來警告,非 debug 用來擋開機。"""
        issues: list[str] = []

        if _looks_unset(self.admin_secret_key):
            issues.append(
                "ADMIN_SECRET_KEY 仍是預設/placeholder 值。這是 admin session 的簽章"
                '金鑰,請用 python -c "import secrets; print(secrets.token_urlsafe(48))" 產生。'
            )
        elif len(self.admin_secret_key) < _MIN_SECRET_LENGTH:
            issues.append(
                f"ADMIN_SECRET_KEY 只有 {len(self.admin_secret_key)} 字元,至少需要 {_MIN_SECRET_LENGTH} 字元。"
            )

        if _looks_unset(self.admin_username):
            issues.append("ADMIN_USERNAME 未設定或仍是預設值。")
        if _looks_unset(self.admin_password):
            issues.append("ADMIN_PASSWORD 未設定或仍是預設/弱密碼。")
        if _looks_unset(self.db_password):
            issues.append("DB_PASSWORD 仍是開發預設值。")
        if _looks_unset(self.redis_password):
            issues.append("REDIS_PASSWORD 仍是開發預設值。")

        if "*" in self.cors_origins:
            issues.append("CORS_ORIGINS 不可是 *,請列出前端的實際網址。")
        insecure_origins = [o for o in self.cors_origins if not o.startswith("https://")]
        if insecure_origins:
            issues.append(f"CORS_ORIGINS 必須是 https:// 開頭: {', '.join(insecure_origins)}")

        # 選用功能:有啟用才檢查它的機密
        if self.google_oauth_client_id:
            if _looks_unset(self.google_oauth_client_secret):
                issues.append("GOOGLE_OAUTH_CLIENT_SECRET 未設定或仍是 placeholder。")
            if not self.frontend_base_url.startswith("https://"):
                issues.append("FRONTEND_BASE_URL 必須是 https:// 開頭(一次性登入碼會放在導回前端的網址上)。")
        if self.storage_backend == "s3" and _looks_unset(self.s3_bucket):
            issues.append("STORAGE_BACKEND=s3 但 S3_BUCKET 未設定。")
        if self.aws_access_key_id and _looks_unset(self.aws_secret_access_key):
            issues.append("有設 AWS_ACCESS_KEY_ID 但 AWS_SECRET_ACCESS_KEY 未設定或仍是 placeholder。")
        if self.smtp_host and _looks_unset(self.smtp_password):
            issues.append("有設 SMTP_HOST 但 SMTP_PASSWORD 未設定或仍是 placeholder。")
        if self.line_channel_access_token and _looks_unset(self.line_channel_secret):
            issues.append("有設 LINE_CHANNEL_ACCESS_TOKEN 但 LINE_CHANNEL_SECRET 未設定(webhook 無法驗簽)。")
        for provider in self.llm_providers:
            key = getattr(self, f"{provider}_api_key", None)
            if key is None:
                issues.append(f"LLM_PROVIDERS 含未知的 provider: {provider}(可用 anthropic、openai、gemini)。")
            elif _looks_unset(key):
                issues.append(f"LLM_PROVIDERS 含 {provider},但 {provider.upper()}_API_KEY 未設定或仍是 placeholder。")

        return issues

    def enforce_secure_settings(self) -> list[str]:
        """啟動時呼叫。

        非 debug 環境:任一項不合格就 raise,讓服務「開不起來」而不是「不安全地
        跑起來」—— 後者才是 2026-07 那次事故能悄悄成立的原因。
        debug 環境:只回傳問題清單讓呼叫端印警告,不擋本機開發。
        """
        issues = self.security_issues()
        if issues and not self.debug:
            detail = "\n".join(f"  - {i}" for i in issues)
            raise RuntimeError(
                "偵測到不安全的設定,拒絕在 DEBUG=False 的環境啟動:\n"
                f"{detail}\n"
                "請依 .env.prod.example 的說明填入實際值後再啟動。"
            )
        return issues


config = Config()
