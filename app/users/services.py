"""User business logic services."""

from loguru import logger
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.users.models import User
from app.users.schemas import UserCreate, UserUpdate


class UserService:
    """User business logic service."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db

    def list_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """
        List all users with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of users, newest first
        """
        logger.debug(f"[Service] Listing users - skip: {skip}, limit: {limit}")
        users = self.db.query(User).order_by(User.id.desc()).offset(skip).limit(limit).all()
        logger.info(f"[Service] Retrieved {len(users)} users")
        return users

    def get_user(self, user_id: int) -> User:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User instance

        Raises:
            NotFoundException: If user not found
        """
        logger.debug(f"[Service] Getting user - user_id: {user_id}")
        user = self.db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.warning(f"[Service] User not found - user_id: {user_id}")
            raise NotFoundException(f"User with id {user_id} not found")

        logger.info(f"[Service] User retrieved - user_id: {user_id}, name: {user.name}")
        return user

    def create_user(self, user_data: UserCreate) -> User:
        """
        Create a new user.

        Args:
            user_data: User creation data

        Returns:
            Created user

        Raises:
            ConflictException: If the name is already taken
        """
        logger.info(f"[Service] Creating user - name: {user_data.name}")

        # Business logic: Check for duplicate names
        existing = self.db.query(User).filter(User.name == user_data.name).first()
        if existing:
            logger.warning(f"[Service] Duplicate user name - name: {user_data.name}, existing_id: {existing.id}")
            raise ConflictException(f"User with name '{user_data.name}' already exists")

        try:
            user = User(name=user_data.name)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"[Service] User created successfully - user_id: {user.id}, name: {user.name}")
            return user
        except Exception as e:
            self.db.rollback()
            logger.exception(f"[Service] Failed to create user - name: {user_data.name}, error: {e}")
            raise

    def update_user(self, user_id: int, user_data: UserUpdate) -> User:
        """
        Update user information.

        Args:
            user_id: User ID to update
            user_data: Updated user data

        Returns:
            Updated user

        Raises:
            NotFoundException: If user not found
            ConflictException: If the name is already taken
        """
        logger.info(f"[Service] Updating user - user_id: {user_id}")

        user = self.get_user(user_id)  # Raises NotFoundException if not found

        # Business logic: Check for duplicate names (excluding current user)
        existing = self.db.query(User).filter(User.name == user_data.name, User.id != user_id).first()
        if existing:
            logger.warning(f"[Service] Duplicate user name - name: {user_data.name}, existing_id: {existing.id}")
            raise ConflictException(f"User with name '{user_data.name}' already exists")

        try:
            user.name = user_data.name
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"[Service] User updated successfully - user_id: {user.id}, name: {user.name}")
            return user
        except Exception as e:
            self.db.rollback()
            logger.exception(f"[Service] Failed to update user - user_id: {user_id}, error: {e}")
            raise

    def delete_user(self, user_id: int) -> bool:
        """
        Delete a user.

        Args:
            user_id: User ID to delete

        Returns:
            True if deleted

        Raises:
            NotFoundException: If user not found
        """
        logger.info(f"[Service] Deleting user - user_id: {user_id}")

        user = self.get_user(user_id)  # Raises NotFoundException if not found

        try:
            self.db.delete(user)
            self.db.commit()
            logger.info(f"[Service] User deleted successfully - user_id: {user_id}")
            return True
        except Exception as e:
            self.db.rollback()
            logger.exception(f"[Service] Failed to delete user - user_id: {user_id}, error: {e}")
            raise
