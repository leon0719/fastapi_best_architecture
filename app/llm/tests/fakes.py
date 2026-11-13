"""測試只用假的 provider:不打任何 LLM API。"""

from pydantic import BaseModel

from app.common.exceptions import ExternalAPIException
from app.llm.external_services import LLMFallbackError, LLMResult
from app.llm.utils import TokenUsage


class FakeProvider:
    def __init__(self, name: str, model: str, *, outcome: str = "ok", data: dict | None = None) -> None:
        self.name, self.model, self.outcome, self.data = name, model, outcome, data or {}
        self.calls = 0

    def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> LLMResult[T]:
        self.calls += 1
        if self.outcome == "fallback":
            raise LLMFallbackError(self.name, "AuthenticationError")
        if self.outcome == "error":
            raise ExternalAPIException(f"{self.name} 服務暫時無法使用")
        return LLMResult(
            parsed=schema.model_validate(self.data),
            provider=self.name,
            model=self.model,
            usage=TokenUsage(input_tokens=1_000_000, cached_tokens=200_000, output_tokens=100_000),
            latency_ms=12,
        )
