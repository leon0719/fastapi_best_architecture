"""Chatbot API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user, require_role
from app.chatbots.schemas import ChatbotCreate, ChatbotRead, ChatbotUpdate
from app.chatbots.services import ChatbotService
from app.common.db.database import get_db
from app.common.schemas import BaseResponse
from app.users.models import Role, User

# 讀取:登入即可。寫入:system_prompt 會餵給 LLM,等同控制模型行為,只開放 admin。
require_admin = require_role(Role.ADMIN)

router = APIRouter(prefix="/chatbots", tags=["chatbots"], dependencies=[Depends(current_user)])


def get_chatbot_service(db: Annotated[Session, Depends(get_db)]) -> ChatbotService:
    return ChatbotService(db)


@router.get("", response_model=BaseResponse[list[ChatbotRead]])
def list_chatbots(
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    return BaseResponse(data=service.list_chatbots(skip=skip, limit=limit))


@router.post("", response_model=BaseResponse[ChatbotRead], status_code=201)
def create_chatbot(
    chatbot: ChatbotCreate,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
    admin: Annotated[User, Depends(require_admin)],
):
    return BaseResponse(data=service.create_chatbot(chatbot, actor=f"user:{admin.id}"))


@router.get("/{chatbot_id}", response_model=BaseResponse[ChatbotRead])
def get_chatbot(
    chatbot_id: int,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
):
    return BaseResponse(data=service.get_chatbot(chatbot_id))


@router.put("/{chatbot_id}", response_model=BaseResponse[ChatbotRead])
def update_chatbot(
    chatbot_id: int,
    chatbot: ChatbotUpdate,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
    admin: Annotated[User, Depends(require_admin)],
):
    return BaseResponse(data=service.update_chatbot(chatbot_id, chatbot, actor=f"user:{admin.id}"))


@router.delete("/{chatbot_id}", response_model=BaseResponse[None])
def delete_chatbot(
    chatbot_id: int,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
    admin: Annotated[User, Depends(require_admin)],
):
    service.delete_chatbot(chatbot_id, actor=f"user:{admin.id}")
    return BaseResponse()
