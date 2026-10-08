"""Chatbot business logic services."""

from loguru import logger
from sqlalchemy.orm import Session

from app.chatbots.models import Chatbot
from app.chatbots.schemas import ChatbotCreate, ChatbotUpdate
from app.common.exceptions import ConflictException, NotFoundException


class ChatbotService:
    """Chatbot business logic service."""

    def __init__(self, db: Session):
        self.db = db

    def list_chatbots(self, skip: int = 0, limit: int = 100) -> list[Chatbot]:
        logger.debug(f"[Service] Listing chatbots - skip: {skip}, limit: {limit}")
        chatbots = self.db.query(Chatbot).order_by(Chatbot.id.desc()).offset(skip).limit(limit).all()
        logger.info(f"[Service] Retrieved {len(chatbots)} chatbots")
        return chatbots

    def get_chatbot(self, chatbot_id: int) -> Chatbot:
        logger.debug(f"[Service] Getting chatbot - chatbot_id: {chatbot_id}")
        chatbot = self.db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
        if not chatbot:
            raise NotFoundException(f"Chatbot with id {chatbot_id} not found")
        return chatbot

    def create_chatbot(self, data: ChatbotCreate) -> Chatbot:
        logger.info(f"[Service] Creating chatbot - name: {data.name}")
        existing = self.db.query(Chatbot).filter(Chatbot.name == data.name).first()
        if existing:
            raise ConflictException(f"Chatbot with name '{data.name}' already exists")

        chatbot = Chatbot(
            name=data.name,
            description=data.description,
            system_prompt=data.system_prompt,
            is_active=data.is_active,
        )
        self.db.add(chatbot)
        self.db.commit()
        self.db.refresh(chatbot)
        return chatbot

    def update_chatbot(self, chatbot_id: int, data: ChatbotUpdate) -> Chatbot:
        chatbot = self.get_chatbot(chatbot_id)
        if data.name is not None:
            existing = self.db.query(Chatbot).filter(Chatbot.name == data.name, Chatbot.id != chatbot_id).first()
            if existing:
                raise ConflictException(f"Chatbot with name '{data.name}' already exists")
            chatbot.name = data.name
        if data.description is not None:
            chatbot.description = data.description
        if data.system_prompt is not None:
            chatbot.system_prompt = data.system_prompt
        if data.is_active is not None:
            chatbot.is_active = data.is_active
        self.db.commit()
        return chatbot

    def delete_chatbot(self, chatbot_id: int) -> bool:
        chatbot = self.get_chatbot(chatbot_id)
        self.db.delete(chatbot)
        self.db.commit()
        return True
