"""User Pydantic schemas for request/response."""

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    name: str = Field(..., min_length=1, max_length=100, description="User name")


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    name: str = Field(..., min_length=1, max_length=100, description="User name")


class UserRead(BaseModel):
    """Schema for reading user data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
