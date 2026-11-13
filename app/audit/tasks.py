"""稽核紀錄保留期清理排程。"""

from sqlalchemy.orm import Session

from app.audit.services import AuditService
from app.common.core.config import config
from app.jobs.scheduler import PeriodicTask


class AuditRetentionTask(PeriodicTask):
    name = "audit.purge_expired"
    interval_seconds = 24 * 3600

    def run(self, db: Session) -> str:
        return f"deleted: {AuditService(db).purge_older_than(config.audit_retention_days)}"
