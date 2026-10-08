"""Chatbot API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.chatbots.schemas import ChatbotCreate, ChatbotRead, ChatbotUpdate
from app.chatbots.services import ChatbotService
from app.common.db.database import get_db
from app.common.schemas import BaseResponse

router = APIRouter(prefix="/chatbots", tags=["chatbots"])


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
):
    return BaseResponse(data=service.create_chatbot(chatbot))


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
):
    return BaseResponse(data=service.update_chatbot(chatbot_id, chatbot))


@router.delete("/{chatbot_id}", response_model=BaseResponse[None])
def delete_chatbot(
    chatbot_id: int,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
):
    service.delete_chatbot(chatbot_id)
    return BaseResponse()
