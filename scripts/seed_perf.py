"""建立壓測帳號並發 session token,JSON 印到 stdout(make perf-seed 轉存到 perf/.perf_users.json)。

只准在 DEBUG=True(本機/開發)環境跑:直接發 token 等於繞過 Google 登入。
用法: python -m scripts.seed_perf [人數,預設 20]
"""

import json
import sys

import app.main  # noqa: F401  # 載入所有 model
from app.auth.dependencies import get_google_client
from app.auth.services import AuthService
from app.common.core.config import config
from app.common.db.database import get_session_factory
from app.users.models import Role, User

EMAIL_DOMAIN = "perf.invalid"  # .invalid 是保留 TLD,不會寄到真的信箱


def seed(count: int) -> list[dict[str, str]]:
    accounts = []
    with get_session_factory()() as db:
        auth = AuthService(db, get_google_client())
        for i in range(count):
            email = f"perf{i}@{EMAIL_DOMAIN}"
            user = db.query(User).filter(User.email == email).one_or_none()
            if user is None:
                # 第一個是 admin(壓 admin 才能用的端點),其餘一般使用者
                user = User(name=f"perf{i}", email=email, role=Role.ADMIN if i == 0 else Role.USER)
                db.add(user)
                db.commit()
            accounts.append({"email": email, "role": user.role, "token": auth.issue_session(user.id)})
    return accounts


def main(argv: list[str]) -> int:
    if not config.debug:
        print("拒絕執行:只能在 DEBUG=True 的環境建立壓測帳號", file=sys.stderr)  # noqa: T201  # CLI 輸出
        return 1
    count = int(argv[0]) if argv else 20
    print(json.dumps(seed(count), ensure_ascii=False, indent=2))  # noqa: T201  # CLI 輸出(轉存成檔案)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
