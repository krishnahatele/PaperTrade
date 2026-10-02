"""Domain errors and their HTTP mapping."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class MarketOSError(Exception):
    """Base class for expected, user-facing errors."""

    status_code: int = 400
    code: str = "marketos_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(MarketOSError):
    status_code = 404
    code = "not_found"


class ConflictError(MarketOSError):
    status_code = 409
    code = "conflict"


class FeatureDisabledError(MarketOSError):
    """Raised when a capability exists in the interface but is not enabled yet."""

    status_code = 403
    code = "feature_disabled"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MarketOSError)
    async def _handle(_: Request, exc: MarketOSError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
