"""業務層稽核:record_audit 與保留期清理。

record_audit 只把紀錄加進 session、不 commit:一定要在被改資料的那次 commit 之前呼叫,
資料成功紀錄才在,資料 rollback 紀錄也不留(同一個交易)。

    user.role = new_role
    record_audit(db, action="update", target=user, before=before, after=snapshot(user), actor=f"user:{me.id}")
    db.commit()
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import delete, inspect
from sqlalchemy.orm import Session

from app.audit.models import AuditLog, AuditSource
from app.audit.utils import diff, plain
from app.common.core.request_context import get_request_id

_SKIPPED_FIELDS = frozenset({"created_at", "updated_at"})


def snapshot(obj: Any) -> dict[str, Any]:
    """ORM 物件的欄位值(不含主鍵與時間戳),給 record_audit 的 before/after 用。

    用 getattr 而不是只讀已載入的值:commit 後屬性會過期,getattr 會重新載入。
    """
    snap: dict[str, Any] = {}
    for attr in inspect(obj).mapper.column_attrs:
        if attr.key not in _SKIPPED_FIELDS and not attr.columns[0].primary_key:
            snap[attr.key] = plain(getattr(obj, attr.key))
    return snap


def record_audit(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: object = None,
    target_label: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor: str | None = None,
    source: AuditSource = AuditSource.API,
    ip: str | None = None,
    masked: frozenset[str] = frozenset(),
) -> AuditLog:
    """加一筆稽核紀錄到 session(不 commit,跟著呼叫端的交易寫入)。"""
    row = AuditLog(
        source=source,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        target_label=None if target_label is None else target_label[:200],
        changes=diff(before or {}, after or {}, masked),
        ip=ip,
        request_id=get_request_id(),
    )
    db.add(row)
    logger.info(f"[Audit] {action} {target_type} - target_id: {target_id}, actor: {actor or '-'}, source: {source}")
    return row


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AuditService:
    def __init__(self, db: Session, now: Callable[[], datetime] = _utc_now) -> None:
        self.db = db
        self.now = now

    def purge_older_than(self, days: int) -> int:
        """刪掉超過保留天數的紀錄(排程呼叫),回傳刪除筆數;days <= 0 表示永久保存,不刪。"""
        if days <= 0:
            return 0
        cutoff = self.now() - timedelta(days=days)
        try:
            result = self.db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception(f"[Service] Failed to purge audit logs - retention_days: {days}")
            raise
        deleted = int(getattr(result, "rowcount", 0) or 0)
        logger.info(f"[Service] Purged audit logs - total: {deleted}, retention_days: {days}")
        return deleted
