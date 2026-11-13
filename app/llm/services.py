"""LLM:依設定的 fallback chain 呼叫、Pydantic structured output、用量與成本記到 llm_usage。

    class Summary(BaseModel):
        title: str
        bullets: list[str]

    summary = LLMService().generate("請摘要:...", Summary, system="你是…", feature="ticket_summary")

- LLM_PROVIDERS=anthropic,openai,gemini:依序嘗試;認證/權限/額度錯誤才換下一家,其他錯誤直接 502。
- 用量另開 session 寫入(不碰呼叫端的交易);寫入失敗只記 log,不讓記帳失敗把結果丟掉。
- 呼叫要數秒到數十秒:放在同步 endpoint 或長任務(app/jobs)裡,不要在 async 函式裡直接呼叫。
"""

from collections.abc import Callable

from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.common.db.database import get_session_factory
from app.common.exceptions import ExternalAPIException
from app.llm.external_services import LLMFallbackError, LLMProvider, LLMResult, build_providers
from app.llm.models import LlmUsage
from app.llm.utils import cost_usd


class LLMService:
    def __init__(
        self,
        providers: list[LLMProvider] | None = None,
        usage_sessions: Callable[[], Session] | None = None,
    ) -> None:
        self.providers = build_providers() if providers is None else providers
        self._usage_sessions = usage_sessions

    def generate[T: BaseModel](
        self, prompt: str, schema: type[T], *, system: str = "", feature: str | None = None
    ) -> T:
        if not self.providers:
            logger.warning(f"[Service] LLM not configured - feature: {feature}")
            raise ExternalAPIException("LLM 服務未設定")
        for provider in self.providers:
            try:
                result = provider.generate(system=system, prompt=prompt, schema=schema)
            except LLMFallbackError as e:
                logger.warning(
                    f"[Service] LLM provider unavailable, trying next - provider: {e.provider}, feature: {feature}"
                )
                continue
            self._record(result, feature)
            logger.info(
                f"[Service] LLM call done - provider: {result.provider}, model: {result.model}, feature: {feature}, "
                f"input_tokens: {result.usage.input_tokens}, output_tokens: {result.usage.output_tokens}, "
                f"duration: {result.latency_ms / 1000:.3f}s"
            )
            return result.parsed
        logger.error(f"[Service] All LLM providers unavailable - feature: {feature}, total: {len(self.providers)}")
        raise ExternalAPIException("LLM 服務暫時無法使用,請稍後再試")

    def _record(self, result: LLMResult, feature: str | None) -> None:
        row = LlmUsage(
            provider=result.provider,
            model=result.model,
            feature=feature,
            input_tokens=result.usage.input_tokens,
            cached_tokens=result.usage.cached_tokens,
            output_tokens=result.usage.output_tokens,
            cost_usd=cost_usd(result.model, result.usage),
            latency_ms=result.latency_ms,
        )
        try:
            with (self._usage_sessions or get_session_factory())() as db:
                db.add(row)
                db.commit()
        except Exception:  # noqa: BLE001  # 記帳失敗不能讓已經付費拿到的結果丟掉;logger.exception 會回報
            logger.exception(f"[Service] Failed to record LLM usage - provider: {result.provider}")
