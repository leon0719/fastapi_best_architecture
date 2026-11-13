"""Admin view for LLM usage(唯讀;按月彙總用 `make llm-cost`)。"""

from sqladmin import ModelView

from app.llm.models import LlmUsage


class LlmUsageAdmin(ModelView, model=LlmUsage):
    name = "LLM Usage"
    name_plural = "LLM Usage"
    icon = "fa-solid fa-coins"

    column_list = [
        LlmUsage.created_at,
        LlmUsage.provider,
        LlmUsage.model,
        LlmUsage.feature,
        LlmUsage.input_tokens,
        LlmUsage.cached_tokens,
        LlmUsage.output_tokens,
        LlmUsage.cost_usd,
        LlmUsage.latency_ms,
    ]
    column_default_sort = [(LlmUsage.id, True)]
    can_create = False
    can_edit = False
    can_delete = False
