"""Custom exception classes for the application."""


class AppException(Exception):
    """Base exception for all application errors.

    The global handler turns it into BaseResponse: {"data": null, "error": {"code": status_code, "message": message}}.
    """

    def __init__(self, message: str, status_code: int = 500):
        """
        Initialize application exception.

        Args:
            message: Error message
            status_code: HTTP status code (also the `error.code` in the response body)
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(AppException):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        """
        Initialize not found exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=404)


class BadRequestException(AppException):
    """Exception raised for invalid request data."""

    def __init__(self, message: str = "Bad request"):
        """
        Initialize bad request exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=400)


class ValidationException(AppException):
    """Exception raised when input validation fails."""

    def __init__(self, message: str = "Validation failed"):
        """
        Initialize validation exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=400)


class ConflictException(AppException):
    """Exception raised when there's a conflict (e.g., duplicate resource)."""

    def __init__(self, message: str = "Resource conflict"):
        """
        Initialize conflict exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=409)


class UnauthorizedException(AppException):
    """Exception raised for authentication failures."""

    def __init__(self, message: str = "Unauthorized"):
        """
        Initialize unauthorized exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=401)


class ForbiddenException(AppException):
    """Exception raised for authorization failures."""

    def __init__(self, message: str = "Forbidden"):
        """
        Initialize forbidden exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=403)


class ExternalAPIException(AppException):
    """Exception raised when external API calls fail."""

    def __init__(self, message: str = "External API error"):
        """
        Initialize external API exception.

        Args:
            message: Error message
        """
        super().__init__(message, status_code=502)
