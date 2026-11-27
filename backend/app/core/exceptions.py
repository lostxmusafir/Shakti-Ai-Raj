from typing import Any, Optional, Dict

class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(self.message)

class NotFoundError(AppException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code=f"{resource.upper()}_NOT_FOUND",
            message=f"{resource.capitalize()} '{identifier}' was not found.",
            status_code=404,
        )

class UnauthorizedError(AppException):
    def __init__(self, message: str = "Invalid or expired authentication credentials."):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401,
        )

class ForbiddenError(AppException):
    def __init__(self, message: str = "You do not have permission to access this resource."):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403,
        )

class PlanValidationError(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="PLAN_INVALID",
            message=message,
            status_code=422,
            details=details,
        )

class ExecutionError(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="EXECUTION_FAILED",
            message=message,
            status_code=500,
            details=details,
        )

class VerificationError(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="VERIFICATION_FAILED",
            message=message,
            status_code=422,
            details=details,
        )

class RateLimitError(AppException):
    def __init__(self, message: str, headers: Dict[str, str]):
        super().__init__(
            code="RATE_LIMITED",
            message=message,
            status_code=429,
            headers=headers,
        )
