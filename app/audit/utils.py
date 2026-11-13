"""稽核用的純函式:欄位 diff、機密遮罩、轉成 JSON 存得下的值。"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

# 欄位名包含這些字就只記「有變更」:軌跡表任何進得了後台的人都看得到,不能變成第二份機密清單
SENSITIVE_MARKERS = ("password", "secret", "token", "digest", "challenge", "api_key", "bank_account")
MASK = "（已變更）"


def is_sensitive(field: str, extra: frozenset[str] = frozenset()) -> bool:
    lowered = field.lower()
    return field in extra or any(m in lowered for m in SENSITIVE_MARKERS)


def plain(value: Any) -> Any:
    """轉成 JSON 欄位存得下的值。"""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return plain(value.value)
    if isinstance(value, date):  # datetime 也是 date
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def diff(before: dict[str, Any], after: dict[str, Any], masked: frozenset[str] = frozenset()) -> dict[str, list[Any]]:
    """{欄位: [舊值, 新值]},只放有變的欄位;機密欄位的值換成 MASK(None 保持 None,看得出設定/清除)。"""
    changes: dict[str, list[Any]] = {}
    for field in sorted({*before, *after}):
        old, new = plain(before.get(field)), plain(after.get(field))
        if old == new:
            continue
        if is_sensitive(field, masked):
            old = None if old is None else MASK
            new = None if new is None else MASK
        changes[field] = [old, new]
    return changes
