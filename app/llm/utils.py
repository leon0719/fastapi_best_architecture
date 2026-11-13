"""LLM 純函式:單價表與成本計算。"""

from dataclasses import dataclass
from decimal import Decimal

# USD / 1M tokens:(input, cached input, output)。單價表沒有的模型照樣記 token,cost_usd 留 NULL。
# 調價或換模型時更新這裡;以各家官方價目表為準(Anthropic 取自 2026-11 的公告,OpenAI / Gemini 請上線前再核對)。
PRICES: dict[str, tuple[str, str, str]] = {
    "claude-opus-5-5": ("4.00", "0.20", "20.00"),
    "claude-sonnet-5-5": ("2.00", "0.10", "10.00"),
    "gpt-5-mini": ("0.25", "0.025", "2.00"),
    "gemini-2.5-flash": ("0.30", "0.075", "2.50"),
}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int  # 含 cached_tokens
    cached_tokens: int
    output_tokens: int


def cost_usd(model: str, usage: TokenUsage) -> Decimal | None:
    price = PRICES.get(model)
    if price is None:
        return None
    input_price, cached_price, output_price = (Decimal(p) for p in price)
    uncached = max(usage.input_tokens - usage.cached_tokens, 0)
    total = uncached * input_price + usage.cached_tokens * cached_price + usage.output_tokens * output_price
    return (total / 1_000_000).quantize(Decimal("0.000001"))
