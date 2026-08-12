"""Chatbot API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.chatbots.schemas import ChatbotCreate, ChatbotRead, ChatbotUpdate
from app.chatbots.services import ChatbotService
from app.common.db.database import get_db

router = APIRouter(prefix="/chatbots", tags=["chatbots"])


def get_chatbot_service(db: Annotated[Session, Depends(get_db)]) -> ChatbotService:
    return ChatbotService(db)


@router.get("", response_model=list[ChatbotRead])
def list_chatbots(
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    return service.list_chatbots(skip=skip, limit=limit)


@router.post("", response_model=ChatbotRead, status_code=201)
def create_chatbot(
    chatbot: ChatbotCreate,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
):
    return service.create_chatbot(chatbot)


@router.get("/{chatbot_id}", response_model=ChatbotRead)
def get_chatbot(
    chatbot_id: int,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
):
    return service.get_chatbot(chatbot_id)


@router.put("/{chatbot_id}", response_model=ChatbotRead)
def update_chatbot(
    chatbot_id: int,
    chatbot: ChatbotUpdate,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
):
    return service.update_chatbot(chatbot_id, chatbot)


@router.delete("/{chatbot_id}", status_code=204)
def delete_chatbot(
    chatbot_id: int,
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
):
    service.delete_chatbot(chatbot_id)
