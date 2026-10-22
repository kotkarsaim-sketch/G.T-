"""Authenticated admin routes (api-spec §2.7): review queue, publish, audit."""

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from civic import auditlog, review
from civic.auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class PublishRequest(BaseModel):
    effective_on: Date | None = None


@router.get("/pending")
async def pending_queue() -> dict:
    return {"items": await review.list_pending()}


@router.post("/instruments/{number}/publish")
async def publish_instrument(number: str, body: PublishRequest | None = None) -> dict:
    effective = body.effective_on if body and body.effective_on else Date.today()
    try:
        published = await review.publish(number, effective)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": str(exc)}) from None
    return {"published": published, "effective_on": effective.isoformat()}


@router.get("/audit")
async def audit_recent(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"items": await auditlog.recent(limit)}


@router.get("/audit/stats")
async def audit_stats() -> dict:
    return await auditlog.stats()


@router.get("/audit/{query_id}")
async def audit_one(query_id: str) -> dict:
    record = await auditlog.one(query_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": "no such query_id"})
    return {"record": record}
