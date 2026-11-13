"""過期登入碼與 session 清理排程。"""

from sqlalchemy.orm import Session

from app.auth.dependencies import get_google_client
from app.auth.services import AuthService
from app.jobs.scheduler import PeriodicTask


class ExpiredTokenCleanupTask(PeriodicTask):
    name = "auth.purge_expired_tokens"
    interval_seconds = 24 * 3600

    def run(self, db: Session) -> str:
        return f"deleted: {AuthService(db, get_google_client()).purge_expired()}"
