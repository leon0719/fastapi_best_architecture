"""User API routes (admin only)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.common.db.database import get_db
from app.common.exports import ExportFormat, table_export_response
from app.common.schemas import BaseResponse
from app.users.models import Role, User
from app.users.schemas import UserCreate, UserRead, UserUpdate
from app.users.services import UserService

# 管理帳號是 admin 才能做的事。同一個依賴物件掛在 router 與參數上,FastAPI 一個請求只驗證一次。
require_admin = require_role(Role.ADMIN)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


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


@router.get("/export")
def export_users(
    service: Annotated[UserService, Depends(get_user_service)],
    format: Annotated[ExportFormat, Query(description="xlsx / pdf / zip")] = ExportFormat.XLSX,
):
    """
    Download all users as xlsx / pdf / zip (file download, not BaseResponse).

    Must be declared before `/{user_id}`, otherwise "export" is parsed as a user id.
    """
    headers, rows = service.export_rows()
    basename = f"使用者清單_{datetime.now(UTC):%Y%m%d}"
    return table_export_response(format, "使用者清單", headers, rows, basename)


@router.post("", response_model=BaseResponse[UserRead], status_code=201)
def create_user(
    user: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Create a new user.

    Args:
        user: User creation data
        service: User service dependency
        admin: The signed-in admin (recorded in the audit log)

    Returns:
        Created user

    Raises:
        ConflictException: If the name is already taken
    """
    return BaseResponse(data=service.create_user(user, actor=f"user:{admin.id}"))


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
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Update user information.

    Args:
        user_id: User ID to update
        user: Updated user data
        service: User service dependency
        admin: The signed-in admin (recorded in the audit log)

    Returns:
        Updated user data

    Raises:
        NotFoundException: If user not found
        ConflictException: If the name is already taken
    """
    return BaseResponse(data=service.update_user(user_id, user, actor=f"user:{admin.id}"))


@router.delete("/{user_id}", response_model=BaseResponse[None])
def delete_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Delete a user.

    Args:
        user_id: User ID to delete
        service: User service dependency
        admin: The signed-in admin (recorded in the audit log)

    Returns:
        Empty BaseResponse (data is null)

    Raises:
        NotFoundException: If user not found
    """
    service.delete_user(user_id, actor=f"user:{admin.id}")
    return BaseResponse()
