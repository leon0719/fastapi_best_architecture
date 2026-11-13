"""LLMService:fallback chain、structured output、用量記帳。只用 FakeProvider。"""

from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.common.core.config import config
from app.common.exceptions import ExternalAPIException
from app.llm.external_services import build_providers
from app.llm.models import LlmUsage
from app.llm.services import LLMService
from app.llm.tests.fakes import FakeProvider
from app.llm.utils import TokenUsage, cost_usd

pytestmark = pytest.mark.unit


class Summary(BaseModel):
    title: str
    tags: list[str]


DATA = {"title": "標題", "tags": ["a"]}


def test_returns_parsed_model_and_records_usage(session_factory, db_session):
    provider = FakeProvider("anthropic", "claude-sonnet-5-5", data=DATA)

    result = LLMService([provider], usage_sessions=session_factory).generate("p", Summary, feature="demo")

    assert result == Summary(title="標題", tags=["a"])
    row = db_session.query(LlmUsage).one()
    assert (row.provider, row.model, row.feature) == ("anthropic", "claude-sonnet-5-5", "demo")
    # 800k 未快取 × $2 + 200k 快取 × $0.10 + 100k 輸出 × $10 = 1.6 + 0.02 + 1.0
    assert row.cost_usd == Decimal("2.620000")


def test_falls_back_on_auth_or_quota_error(session_factory):
    first = FakeProvider("anthropic", "m1", outcome="fallback")
    second = FakeProvider("openai", "gpt-5-mini", data=DATA)

    LLMService([first, second], usage_sessions=session_factory).generate("p", Summary)

    assert (first.calls, second.calls) == (1, 1)


def test_other_errors_do_not_fall_back(session_factory):
    first = FakeProvider("anthropic", "m1", outcome="error")
    second = FakeProvider("openai", "m2", data=DATA)

    with pytest.raises(ExternalAPIException):
        LLMService([first, second], usage_sessions=session_factory).generate("p", Summary)
    assert second.calls == 0


def test_all_providers_unavailable(session_factory):
    service = LLMService([FakeProvider("a", "m", outcome="fallback")], usage_sessions=session_factory)

    with pytest.raises(ExternalAPIException, match="暫時無法使用"):
        service.generate("p", Summary)


def test_not_configured():
    with pytest.raises(ExternalAPIException, match="未設定"):
        LLMService([]).generate("p", Summary)


def test_unknown_model_has_null_cost(session_factory, db_session):
    LLMService([FakeProvider("x", "unknown-model", data=DATA)], usage_sessions=session_factory).generate("p", Summary)

    assert db_session.query(LlmUsage).one().cost_usd is None


def test_usage_recording_failure_does_not_lose_result():
    def broken_sessions():
        raise RuntimeError("db down")

    service = LLMService([FakeProvider("x", "m", data=DATA)], usage_sessions=broken_sessions)

    assert service.generate("p", Summary).title == "標題"


def test_cost_usd():
    assert cost_usd("gpt-5-mini", TokenUsage(1_000_000, 0, 0)) == Decimal("0.250000")
    assert cost_usd("nope", TokenUsage(1, 0, 1)) is None


def test_build_providers_skips_unconfigured(monkeypatch):
    monkeypatch.setattr(config, "llm_providers", ["anthropic", "openai"])
    monkeypatch.setattr(config, "anthropic_api_key", "")
    monkeypatch.setattr(config, "openai_api_key", "")

    assert build_providers() == []
