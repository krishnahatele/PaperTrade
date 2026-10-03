"""Health endpoints (unversioned, used by Docker / orchestrators)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep
from app.schemas.system import ComponentCheck, LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=LivenessResponse, summary="Liveness probe")
@router.get("/live", response_model=LivenessResponse, include_in_schema=False)
async def live() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (checks database)",
    responses={503: {"model": ReadinessResponse}},
)
async def ready(container: ContainerDep, response: Response) -> ReadinessResponse:
    checks: list[ComponentCheck] = []
    try:
        await container.db.ping()
        checks.append(ComponentCheck(name="database", ok=True))
    except Exception as exc:  # report any connectivity failure, never raise
        checks.append(ComponentCheck(name="database", ok=False, detail=type(exc).__name__))

    ok = all(c.ok for c in checks)
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if ok else "degraded", checks=checks)
