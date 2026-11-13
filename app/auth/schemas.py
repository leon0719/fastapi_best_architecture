"""登入相關的請求／回應 schema。"""

from pydantic import BaseModel, ConfigDict, Field


class ExchangeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    # PKCE code_verifier(RFC 7636 的長度範圍,base64url 字元)
    verifier: str = Field(pattern=r"^[A-Za-z0-9_-]{43,128}$")


class TokenRead(BaseModel):
    token: str


class MeRead(BaseModel):
    """目前登入者。roles 是展開後的全部角色(admin → ["admin", "user"]),前端 usePermission 直接比對。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    role: str
    roles: list[str]
