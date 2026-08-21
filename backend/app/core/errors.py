"""
Centralized, friendly error handling.
Business/service code raises these typed exceptions; routes never build
raw HTTPExceptions with internal detail leaking to the client.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger("spar.errors")


class AppError(Exception):
    """Base class for all handled application errors."""
    status_code = 400
    message = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    message = "The requested item was not found."


class ValidationFailedError(AppError):
    status_code = 422
    message = "The submitted data is invalid."


class PermissionDeniedError(AppError):
    status_code = 403
    message = "You do not have permission to perform this action."


class UnauthorizedError(AppError):
    status_code = 401
    message = "Authentication is required."


class ConflictError(AppError):
    status_code = 409
    message = "This action conflicts with existing data."


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Full detail goes to the server log only — never to the client.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Our team has been notified."},
        )
