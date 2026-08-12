"""Chatbot Pydantic schemas for request/response."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatbotCreate(BaseModel):
    """Schema for creating a new chatbot."""

    name: str = Field(..., min_length=1, max_length=100, description="Chatbot name")
    description: str | None = Field(None, description="Chatbot description")
    system_prompt: str | None = Field(None, description="System prompt for chatbot behavior")
    is_active: bool = Field(True, description="Whether chatbot is active")


class ChatbotUpdate(BaseModel):
    """Schema for updating a chatbot."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    system_prompt: str | None = None
    is_active: bool | None = None


class ChatbotRead(BaseModel):
    """Schema for reading chatbot data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    system_prompt: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
