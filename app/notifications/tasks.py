"""通知 outbox 的重送與保留期清理排程。"""

from sqlalchemy.orm import Session

from app.common.core.config import config
from app.jobs.scheduler import PeriodicTask
from app.notifications.services import NotificationService


class OutboxDispatchTask(PeriodicTask):
    name = "notifications.dispatch_outbox"
    interval_seconds = config.notification_retry_interval_seconds
    initial_delay_seconds = 10

    def run(self, db: Session) -> str:
        return str(NotificationService(db).dispatch_pending())


class OutboxRetentionTask(PeriodicTask):
    name = "notifications.purge_outbox"
    interval_seconds = 24 * 3600

    def run(self, db: Session) -> str:
        return f"deleted: {NotificationService(db).purge_finished(config.notification_retention_days)}"
