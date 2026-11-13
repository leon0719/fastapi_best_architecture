"""LLM provider adapter:Anthropic、OpenAI、Gemini。SDK 只能在這個檔案 import 與呼叫。

SDK 是選用依賴(`uv sync --extra llm`),在 adapter 建構時才 import:沒裝 extra 的專案與 CI
照樣能 import 這個模組,只有真的啟用該 provider 才需要套件。

每個 adapter 把 SDK 的錯誤分成兩種:
- LLMFallbackError:認證失敗、權限不足、額度/速率用完 —— 換下一家有意義。
- ExternalAPIException:其他錯誤(5xx、逾時在 SDK 內建重試後仍失敗、拒答、格式不符)—— 不換家,
  免得暫時性錯誤悄悄改變「是哪個模型回答的」。
"""

import time
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger
from pydantic import BaseModel, ValidationError

from app.common.core.config import config
from app.common.exceptions import ExternalAPIException
from app.llm.utils import TokenUsage

_TIMEOUT_SECONDS = 120.0
_MAX_TOKENS = 16000


class LLMFallbackError(Exception):
    """這家用不了(認證、權限、額度),換下一家。"""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider}: {reason}")
        self.provider = provider


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    parsed: T
    provider: str
    model: str  # 實際回答的模型(Anthropic 拒答 fallback 時可能和設定的不同)
    usage: TokenUsage
    latency_ms: int


class LLMProvider(Protocol):
    name: str
    model: str

    def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> LLMResult[T]: ...


def _failed(provider: str, e: Exception) -> ExternalAPIException:
    # 只記例外類別:錯誤訊息可能含 prompt 片段
    logger.warning(f"[External] LLM call failed - provider: {provider}, error_type: {type(e).__name__}")
    return ExternalAPIException(f"{provider} 服務暫時無法使用,請稍後再試")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, refusal_fallback: bool = True) -> None:
        import anthropic

        self._sdk = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=_TIMEOUT_SECONDS, max_retries=2)
        self.model = model
        self._refusal_fallback = refusal_fallback

    def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> LLMResult[T]:
        sdk = self._sdk
        start = time.monotonic()
        extra: dict[str, Any] = {"system": system} if system else {}
        if self._refusal_fallback:
            # 安全分類器拒答時,由 API 依拒答類別自動改用合適的模型重跑(同一個請求內)
            extra |= {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                **extra,
            )
        except (sdk.AuthenticationError, sdk.PermissionDeniedError, sdk.RateLimitError) as e:
            raise LLMFallbackError(self.name, type(e).__name__) from e
        except sdk.APIError as e:
            raise _failed(self.name, e) from e
        if response.stop_reason == "refusal" or response.parsed_output is None:
            logger.warning(
                f"[External] LLM gave no structured output - provider: anthropic, stop: {response.stop_reason}"
            )
            raise ExternalAPIException("anthropic 無法完成這個請求")
        usage = response.usage
        cached = usage.cache_read_input_tokens or 0
        return LLMResult(
            parsed=response.parsed_output,
            provider=self.name,
            model=response.model,
            usage=TokenUsage(
                # Anthropic 的 input_tokens 不含快取讀寫的部分,三者相加才是總輸入
                input_tokens=usage.input_tokens + cached + (usage.cache_creation_input_tokens or 0),
                cached_tokens=cached,
                output_tokens=usage.output_tokens,
            ),
            latency_ms=int((time.monotonic() - start) * 1000),
        )


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        import openai

        self._sdk = openai
        self._client = openai.OpenAI(api_key=api_key, timeout=_TIMEOUT_SECONDS, max_retries=2)
        self.model = model

    def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> LLMResult[T]:
        sdk = self._sdk
        start = time.monotonic()
        try:
            response = self._client.responses.parse(
                model=self.model,
                instructions=system or None,
                input=prompt,
                text_format=schema,
                max_output_tokens=_MAX_TOKENS,
            )
        except (sdk.AuthenticationError, sdk.PermissionDeniedError, sdk.RateLimitError) as e:
            raise LLMFallbackError(self.name, type(e).__name__) from e
        except sdk.OpenAIError as e:
            raise _failed(self.name, e) from e
        if response.output_parsed is None:
            raise ExternalAPIException("openai 無法完成這個請求")
        usage = response.usage
        cached = usage.input_tokens_details.cached_tokens if usage and usage.input_tokens_details else 0
        return LLMResult(
            parsed=response.output_parsed,
            provider=self.name,
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.input_tokens if usage else 0,
                cached_tokens=cached or 0,
                output_tokens=usage.output_tokens if usage else 0,
            ),
            latency_ms=int((time.monotonic() - start) * 1000),
        )


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai
        from google.genai import errors

        self._errors = errors
        self._client = genai.Client(api_key=api_key, http_options={"timeout": int(_TIMEOUT_SECONDS * 1000)})
        self.model = model

    def generate[T: BaseModel](self, *, system: str, prompt: str, schema: type[T]) -> LLMResult[T]:
        start = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "system_instruction": system or None,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
            parsed = schema.model_validate_json(response.text or "")
        except self._errors.ClientError as e:
            if e.code in (401, 403, 429):
                raise LLMFallbackError(self.name, f"HTTP {e.code}") from e
            raise _failed(self.name, e) from e
        except (self._errors.APIError, ValidationError) as e:
            raise _failed(self.name, e) from e
        meta = response.usage_metadata
        return LLMResult(
            parsed=parsed,
            provider=self.name,
            model=self.model,
            usage=TokenUsage(
                input_tokens=(meta.prompt_token_count or 0) if meta else 0,
                cached_tokens=(meta.cached_content_token_count or 0) if meta else 0,
                # thinking 一樣按輸出價計費
                output_tokens=((meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)) if meta else 0,
            ),
            latency_ms=int((time.monotonic() - start) * 1000),
        )


def build_providers() -> list[LLMProvider]:
    """依 LLM_PROVIDERS 的順序建立 fallback chain;沒填 key 的 provider 略過。"""
    providers: list[LLMProvider] = []
    for name in config.llm_providers:
        if name == "anthropic" and config.anthropic_api_key:
            providers.append(AnthropicProvider(config.anthropic_api_key, config.anthropic_model))
        elif name == "openai" and config.openai_api_key:
            providers.append(OpenAIProvider(config.openai_api_key, config.openai_model))
        elif name == "gemini" and config.gemini_api_key:
            providers.append(GeminiProvider(config.gemini_api_key, config.gemini_model))
    return providers
