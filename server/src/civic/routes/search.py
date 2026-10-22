"""Retrieval-only search endpoint (api-spec §2.2)."""

import logging
from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from civic.graph import GraphUnavailable
from civic.retrieval import DependencyUnavailable, new_query_id, search_only

log = logging.getLogger(__name__)
router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=25)
    jurisdiction: str | None = None
    as_of: Date | None = None


@router.post("/search")
async def search(req: SearchRequest) -> dict:
    try:
        sources = await search_only(
            req.query, mode=req.mode, limit=req.limit, as_of=req.as_of
        )
    except (DependencyUnavailable, GraphUnavailable) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "dependency_unavailable", "detail": str(exc)},
        ) from None
    return {
        "query_id": new_query_id(),
        "query": req.query,
        "results": [
            {
                **s.citation_dict(),
                "text": s.text,
            }
            for s in sources
        ],
    }
