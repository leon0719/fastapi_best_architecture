"""Config 應由 pydantic-settings 直接綁定環境變數,而非 os.getenv 預設值。"""

import pytest

pytestmark = pytest.mark.unit


def test_config_reads_env_vars(monkeypatch):
    monkeypatch.setenv("DB_HOST", "example-db")
    monkeypatch.setenv("DB_PORT", "15432")
    monkeypatch.setenv("DEBUG", "true")

    from app.common.core.config import Config

    cfg = Config()
    assert cfg.db_host == "example-db"
    assert cfg.db_port == 15432
    assert cfg.debug is True


def test_db_url_and_redis_url(monkeypatch):
    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("DB_NAME", "n")
    monkeypatch.setenv("DB_PORT", "5432")

    from app.common.core.config import Config

    cfg = Config()
    assert cfg.db_url == "postgresql+psycopg://u:p@h:5432/n"
    assert cfg.redis_url.startswith("redis://:")


def test_no_os_getenv_in_config_source():
    """防止退回 os.getenv 反模式。"""
    import inspect

    from app.common.core import config as config_module

    source = inspect.getsource(config_module)
    assert "os.getenv" not in source
    assert "load_dotenv" not in source
