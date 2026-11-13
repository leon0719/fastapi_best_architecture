# 登入與授權(Google OAuth + PKCE、RBAC)

寫需要登入或限制角色的端點之前讀這份。實作在 `app/auth/`,角色定義在 `app/users/models.py`。

## 端點要求登入 / 角色

```python
from app.auth.dependencies import current_user, require_role
from app.users.models import Role, User

# 任何登入者
def list_mine(user: Annotated[User, Depends(current_user)], ...): ...

# 整個 router 只給 admin(同一個依賴物件掛 router 與參數,一個請求只驗證一次)
require_admin = require_role(Role.ADMIN)
router = APIRouter(prefix="/reports", dependencies=[Depends(require_admin)])
```

- 未登入 → 401 `unauthenticated`;角色不符 → 403 `permission_denied`。
- 「只能看自己的資料」是 service 的責任:查詢條件帶 `owner_id == user.id`,查不到回 404(不要回 403 透露資料存在)。
- 新增角色:在 `Role` 加成員,並在 `ROLE_IMPLIES` 寫它涵蓋哪些角色(admin 涵蓋 user)。DB 存字串,不需要 migration。
- 角色只能在 SQLAdmin 後台改(`UserAdmin` 的下拉選單),變更會進稽核軌跡。

## 登入流程(與前端模板的契約)

```
前端  產生 PKCE verifier(43–128 字元 base64url),challenge = base64url(sha256(verifier))
  ──整頁導轉──▶ GET  /api/v1/auth/google/login?challenge=…      後端把 state + challenge 存進 session cookie
  ◀──302────── Google 登入頁 → GET /api/v1/auth/google/callback  後端驗 state、換 ID token、檢查 email_verified 與 hd
  ◀──302────── {FRONTEND_BASE_URL}/login/callback?code=<一次性登入碼,60 秒>
  ──POST──────▶ /api/v1/auth/exchange {code, verifier}           DELETE … RETURNING 取出登入碼並比對 challenge
  ◀──────────── {"data": {"token": "<opaque session token>"}}    之後 Authorization: Bearer <token>
  ──GET───────▶ /api/v1/auth/me  → {id, name, email, role, roles}   roles 是展開後的全部角色(admin → ["admin","user"])
  ──POST──────▶ /api/v1/auth/logout
```

- 失敗一律導回 `{FRONTEND_BASE_URL}/login?error=<reason>`:`auth_failed`、`forbidden`(email 未驗證、網域不符、帳號停用)、
  `not_registered`、`not_configured`。
- DB 只存 token 的 sha256;原始值只出現在回應一次。登入碼綁定 challenge,別人拿到登入碼也換不到 token;
  verifier 錯一次登入碼就作廢。
- `GOOGLE_AUTO_REGISTER=False`(預設):只有後台先建好 email 的帳號能登入;`True`:第一次登入自動建 role=user。
- `GOOGLE_ALLOWED_DOMAIN` 設定後只接受該 Workspace 網域(比對 ID token 的 `hd`,不是信箱字尾)。
- Google Cloud Console 的 redirect URI:`https://<api 網域>/api/v1/auth/google/callback`(uvicorn 以 `--proxy-headers`
  啟動,`url_for` 才會產生 https)。

## Rate limit

`/auth/google/login`、`/auth/google/callback`、`/auth/exchange` 依來源 IP 限速(`RATE_LIMIT_AUTH`,預設 `10/minute`),
超過回 429 `rate_limited`。其他端點要限速:

```python
from app.common.core.rate_limit import limiter

@router.post("/password-reset")
@limiter.limit("3/minute")          # 或傳函式讀 settings,例如 auth_rate
def reset(request: Request, ...):   # 一定要有 request 參數
```

計數存 Redis(多 worker、多機器共用);`RATE_LIMIT_STORAGE_URI=memory://` 時每個 worker 各算各的,實際上限 =
設定值 × worker 數。來源 IP 讀 nginx 設的 `X-Real-IP`(見 `app/common/core/request_context.py`),所以 app 不能直接對外。

## 測試

- Google 一律用 `app/auth/tests/fakes.py` 的 `FakeGoogle`(dependency override `get_google_client`),不連網。
- 需要登入的端點測試用根目錄 `conftest.py` 的 `make_user(role)`(回傳 user 與 headers)與 `admin_headers`,
  並涵蓋 401 / 403。
