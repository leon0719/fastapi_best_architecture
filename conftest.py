"""測試環境的環境變數基線。

必須在任何 app 模組被 import 之前設定:`app.common.core.config` 在 import 時就
建立 `config = Config()` 單例,而 `app.main` 會拿它跑 enforce_secure_settings()。

沒有這層基線的話,測試會去讀開發者本機的 .env —— 有 .env 的人測試會過,剛 clone
下來的人(或 CI)因為 DEBUG 預設 False 且全是預設值,一 import app.main 就 raise。
測試結果不該取決於某台機器上有沒有那個檔案。

下半部是共用 fixture(放根目錄,tests/ 與 app/*/tests/ 都看得到)。app 模組一律在
fixture 內 import,確保環境變數基線先生效。
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_TEST_ENV = {
    "DEBUG": "true",
    "ADMIN_SECRET_KEY": "test-only-secret-key-not-used-anywhere-real-0123456789",
    "ADMIN_USERNAME": "test-admin",
    "ADMIN_PASSWORD": "test-only-password",
    "DB_PASSWORD": "test-only-db-password",
    "REDIS_PASSWORD": "test-only-redis-password",
}

# setdefault:真實環境變數優先,才不會蓋掉使用者刻意指定的測試設定。
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture()
def db_session():
    """每個測試一個全新的 in-memory SQLite,不需要 Docker,測試間互不影響。"""
    import app.main  # noqa: F401  # 匯入所有 router → 所有 model 都註冊進 Base.metadata
    from app.common.db.database import Base

    # ponytail: SQLite 跑不到 Postgres 專屬行為(timestamptz、部分約束與鎖);那些由 CI 的
    # tests-integration job 在真 Postgres 上跑 alembic 驗證。真要測 Postgres 行為時,改成連
    # Postgres + 每個測試包 savepoint rollback。
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """TestClient whose `get_db` yields the test session (no lifespan, no real DB/Redis)."""
    from app.common.db.database import get_db
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()
