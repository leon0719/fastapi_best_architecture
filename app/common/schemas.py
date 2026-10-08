"""團隊統一回應格式 BaseResponse[T],與 .NET 後端、前端 axiosService 的契約相同。

成功:{"data": <T>, "error": null}
失敗:{"data": null, "error": {"code": <HTTP 狀態碼>, "message": "..."}}
"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """錯誤資訊。"""

    code: int
    message: str


class BaseResponse[T](BaseModel):
    """所有 /api 端點的回應外層。views 一律 `return BaseResponse(data=...)`。"""

    data: T | None = None
    error: ErrorResponse | None = None
