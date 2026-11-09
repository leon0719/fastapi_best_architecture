"""Custom exception classes for the application."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable, machine-readable error codes — become `error.reason` in BaseResponse.

    `error.code` is only the HTTP status; `reason` lets clients tell apart failures that share a
    status (e.g. two different 409s) and use it as an i18n key instead of matching `message`.
    Add new codes here, never pass ad-hoc strings. Values match the Django Ninja template's codes.
    """

    BAD_REQUEST = "bad_request"
    VALIDATION_ERROR = "validation_error"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    EXTERNAL_API_ERROR = "external_api_error"
    INTERNAL_ERROR = "internal_error"
    USER_NAME_TAKEN = "user_name_taken"
    CHATBOT_NAME_TAKEN = "chatbot_name_taken"


class AppException(Exception):
    """Base exception for all application errors.

    The global handler turns it into BaseResponse:
    {"data": null, "error": {"code": status_code, "message": message, "reason": reason}}.
    Subclasses only set `status_code`, a generic `reason` and `default_message`; pass
    `reason=ErrorCode.X` when the client needs to branch on this specific failure.
    """

    status_code: int = 500
    reason: ErrorCode = ErrorCode.INTERNAL_ERROR
    default_message: str = "Internal server error"

    def __init__(self, message: str | None = None, reason: ErrorCode | None = None):
        self.message = message or self.default_message
        if reason is not None:
            self.reason = reason
        super().__init__(self.message)


class NotFoundException(AppException):
    status_code, reason, default_message = 404, ErrorCode.NOT_FOUND, "Resource not found"


class BadRequestException(AppException):
    status_code, reason, default_message = 400, ErrorCode.BAD_REQUEST, "Bad request"


class ValidationException(AppException):
    status_code, reason, default_message = 400, ErrorCode.VALIDATION_ERROR, "Validation failed"


class ConflictException(AppException):
    status_code, reason, default_message = 409, ErrorCode.CONFLICT, "Resource conflict"


class UnauthorizedException(AppException):
    status_code, reason, default_message = 401, ErrorCode.UNAUTHENTICATED, "Unauthorized"


class ForbiddenException(AppException):
    status_code, reason, default_message = 403, ErrorCode.PERMISSION_DENIED, "Forbidden"


class ExternalAPIException(AppException):
    status_code, reason, default_message = 502, ErrorCode.EXTERNAL_API_ERROR, "External API error"
