"""User API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.db.database import get_db
from app.common.schemas import BaseResponse
from app.users.schemas import UserCreate, UserRead, UserUpdate
from app.users.services import UserService

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service(db: Annotated[Session, Depends(get_db)]) -> UserService:
    """Get user service instance."""
    return UserService(db)


@router.get("", response_model=BaseResponse[list[UserRead]])
def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum records to return")] = 100,
):
    """
    List all users with pagination.

    Args:
        skip: Number of records to skip (default: 0)
        limit: Maximum number of records to return (default: 100, max: 1000)
        service: User service dependency

    Returns:
        List of users
    """
    return BaseResponse(data=service.list_users(skip=skip, limit=limit))


@router.post("", response_model=BaseResponse[UserRead], status_code=201)
def create_user(
    user: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Create a new user.

    Args:
        user: User creation data
        service: User service dependency

    Returns:
        Created user

    Raises:
        ConflictException: If the name is already taken
    """
    return BaseResponse(data=service.create_user(user))


@router.get("/{user_id}", response_model=BaseResponse[UserRead])
def get_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Get a specific user by ID.

    Args:
        user_id: User ID to retrieve
        service: User service dependency

    Returns:
        User data

    Raises:
        NotFoundException: If user not found
    """
    return BaseResponse(data=service.get_user(user_id))


@router.put("/{user_id}", response_model=BaseResponse[UserRead])
def update_user(
    user_id: int,
    user: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Update user information.

    Args:
        user_id: User ID to update
        user: Updated user data
        service: User service dependency

    Returns:
        Updated user data

    Raises:
        NotFoundException: If user not found
        ConflictException: If the name is already taken
    """
    return BaseResponse(data=service.update_user(user_id, user))


@router.delete("/{user_id}", response_model=BaseResponse[None])
def delete_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
):
    """
    Delete a user.

    Args:
        user_id: User ID to delete
        service: User service dependency

    Returns:
        Empty BaseResponse (data is null)

    Raises:
        NotFoundException: If user not found
    """
    service.delete_user(user_id)
    return BaseResponse()
