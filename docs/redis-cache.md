# Redis 快取

使用 Redis 快取之前讀這份。實作在 `app/common/core/redis.py`。

## 用法

```python
from app.common.core.redis import RedisCache, cache_result

cache = RedisCache()
cache.set("key", "value", expire=300)                   # 字串，TTL 秒數
cache.set_json("user:123", {"name": "John"}, expire=60)  # JSON 序列化
cache.get("key")
cache.get_json("user:123")
cache.delete("user:123")
cache.incr("counter")
```

裝飾器（key 為 `{key_prefix}:{函式名}:{參數}`，例如 `user:get_profile:123`）：

```python
@cache_result(expire=3600, key_prefix="user")
def get_profile(user_id: int) -> dict:
    ...
```

## 規則

- **一定要設 TTL**，避免記憶體無限成長。
- **只快取可 JSON 序列化的值**：dict 或 `XxxRead.model_validate(obj).model_dump(mode="json")`。不要快取 ORM 物件。
- **Redis 失敗要能降級**：`RedisCache` 的方法失敗時回 `None`／`False` 並記錄 log，不往上拋——呼叫端照常查 DB。
- **寫入後失效**：update／delete 成功後 `cache.delete(...)` 對應的 key。
- key 用階層式命名：`user:123:profile`、`product:456:details`。
- 快取命中／未命中已由 `cache_result` 以 `[Redis]` 前綴記錄。

## 模式

1. **時間型**：`cache.set(key, value, expire=3600)`，到期自動失效。
2. **主動失效**：資料變更後 `cache.delete(key)`。
3. **Cache-aside**：先查快取 → 未命中就查 DB → 寫回快取 → 回傳。
