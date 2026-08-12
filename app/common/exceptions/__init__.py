"""Custom exception classes for the application."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Machine-readable error codes, stable across message wording changes.

    Clients should branch on `error_code`, not on the human-readable message.
    """

    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, status_code: int = 500, code: ErrorCode = ErrorCode.INTERNAL_ERROR):
        """
        Initialize application exception.

        Args:
            message: Error message
            status_code: HTTP status code
            code: Machine-readable error code
        """
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(self.message)


class NotFoundException(AppException):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        """
        Initialize not found exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=404, code=ErrorCode.NOT_FOUND)


class BadRequestException(AppException):
    """Exception raised for invalid request data."""

    def __init__(self, message: str = "Bad request"):
        """
        Initialize bad request exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=400, code=ErrorCode.BAD_REQUEST)


class ValidationException(AppException):
    """Exception raised when input validation fails."""

    def __init__(self, message: str = "Validation failed"):
        """
        Initialize validation exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=400, code=ErrorCode.VALIDATION_FAILED)


class ConflictException(AppException):
    """Exception raised when there's a conflict (e.g., duplicate resource)."""

    def __init__(self, message: str = "Resource conflict"):
        """
        Initialize conflict exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=409, code=ErrorCode.CONFLICT)


class UnauthorizedException(AppException):
    """Exception raised for authentication failures."""

    def __init__(self, message: str = "Unauthorized"):
        """
        Initialize unauthorized exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=401, code=ErrorCode.UNAUTHORIZED)


class ForbiddenException(AppException):
    """Exception raised for authorization failures."""

    def __init__(self, message: str = "Forbidden"):
        """
        Initialize forbidden exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=403, code=ErrorCode.FORBIDDEN)


class ExternalAPIException(AppException):
    """Exception raised when external API calls fail."""

    def __init__(self, message: str = "External API error"):
        """
        Initialize external API exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=502, code=ErrorCode.EXTERNAL_API_ERROR)
