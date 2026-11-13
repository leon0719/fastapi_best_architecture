# LLM(選用模組)

實作在 `app/llm/`。依賴是選用的:`uv sync --extra llm`(Docker 映像要用時把 Dockerfile 的 `uv sync` 加上 `--extra llm`)。

## 用法

```python
class TicketSummary(BaseModel):
    title: str
    priority: Literal["low", "normal", "high"]


summary = LLMService().generate(prompt, TicketSummary, system="你是客服助理…", feature="ticket_summary")
```

- 回傳的是驗證過的 Pydantic 物件(各家 SDK 的 structured output:Anthropic `messages.parse(output_format=…)`、
  OpenAI `responses.parse(text_format=…)`、Gemini `response_schema`)。
- 呼叫需要數秒到數十秒:放在同步 endpoint 或長任務(`app/jobs`),不要放在 async 函式裡。
- `feature` 用來歸屬成本(`llm_usage.feature`)。

## Fallback chain

`LLM_PROVIDERS=anthropic,openai,gemini` 依序嘗試,沒填 API key 的略過。只有**認證失敗、權限不足、額度/速率用完**
(401/403/429)才換下一家;其他錯誤(5xx、逾時在 SDK 內建重試後仍失敗、拒答、輸出不符 schema)直接 502,
免得暫時性錯誤悄悄改變是哪個模型回答的。

預設模型:Anthropic `claude-sonnet-5-5`(並開啟 API 端的拒答 fallback `fallbacks: "default"`)、OpenAI `gpt-5-mini`、
Gemini `gemini-2.5-flash`,都可用 `*_MODEL` 覆寫。

## 用量與成本

每次成功呼叫寫一列 `llm_usage`(provider、實際回答的 model、input/cached/output tokens、cost_usd、latency)。
單價表在 `app/llm/utils.py` 的 `PRICES`(USD / 1M tokens),沒列到的模型 cost 留 NULL;換模型或調價時更新它,
上線前以各家官方價目表核對。

```bash
make llm-cost        # 開發環境:每月 × 模型的呼叫數、token、美金,含月小計
make prod-llm-cost   # 正式環境(由人執行)
```

## 測試

只用假的 provider(`app/llm/tests/fakes.py` 的 `FakeProvider`),不打任何 LLM API、不花錢。
