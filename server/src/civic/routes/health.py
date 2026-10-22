"""Liveness and readiness probes."""

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from civic import embeddings, graph

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def ready() -> Response:
    checks = {"graph": False, "embeddings": False}
    try:
        await graph.read("RETURN 1 AS ok")
        checks["graph"] = True
    except Exception:  # noqa: BLE001 - readiness reports, never raises
        pass
    checks["embeddings"] = await embeddings.healthy()

    ok = all(checks.values())
    body = {"status": "ok" if ok else "degraded", "checks": checks}
    return JSONResponse(body, status_code=200 if ok else 503)
