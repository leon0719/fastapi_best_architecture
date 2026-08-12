import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# ENV 決定要載入哪個 .env 檔:local -> .env.local, prod -> .env.prod。
# 未設定時預設 local,所以本地開發不用特別 export;Docker compose 用 env_file
# 明確指定該環境的檔案,process 環境不會有 ENV,故仍以此變數的預設值為準。
_env = os.getenv("ENV", "local")
_env_file = f".env.{_env}"

_PLACEHOLDER_MARKERS = ("changeme", "your-", "change-in-production")

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
    """

    model_config = SettingsConfigDict(env_file=_env_file, env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Best FastAPI Architecture"
    env: str = "local"
    debug: bool = False

    # Database configuration
    db_host: str = "db"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "fastapi_db"

    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = "redis_password"
    redis_db: int = 0
    redis_decode_responses: bool = True

    # Admin panel configuration (optional for migrations)
    admin_secret_key: str = ""
    admin_username: str = ""
    admin_password: str = ""

    @property
    def db_url(self) -> str:
        """PostgreSQL database URL"""
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        """Redis connection URL"""
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"

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
