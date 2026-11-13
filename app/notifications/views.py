"""LINE Messaging API webhook。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.common.core.config import config
from app.common.schemas import BaseResponse
from app.notifications.services import LineWebhookService

router = APIRouter(prefix="/line", tags=["line"])


def get_line_webhook_service() -> LineWebhookService:
    return LineWebhookService(config.line_channel_secret)


@router.post("/webhook", response_model=BaseResponse[None])
async def line_webhook(
    request: Request,
    service: Annotated[LineWebhookService, Depends(get_line_webhook_service)],
    x_line_signature: Annotated[str | None, Header()] = None,
):
    """簽章要對「原始」body 計算,所以讀 bytes 而不是用 Pydantic model 解析。"""
    service.handle(await request.body(), x_line_signature)
    return BaseResponse()
