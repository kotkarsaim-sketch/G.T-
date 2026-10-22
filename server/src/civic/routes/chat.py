"""Grounded Q&A over SSE (api-spec §2.1)."""

import json
import logging
import time
from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from civic import graph, llm
from civic.citations import validate as validate_citations
from civic.graph import GraphUnavailable
from civic.prompts import (
    DEGRADED_NOTICE,
    REFUSAL_TEXT,
    build_context_block,
    build_system,
)
from civic.retrieval import DependencyUnavailable, new_query_id, retrieve

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish"}


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    jurisdiction: str | None = None
    locale: str = "en"
    as_of: Date | None = None
    history: list[Turn] = Field(default_factory=list, max_length=6)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    started = time.perf_counter()
    query_id = new_query_id()
    language = LANGUAGE_NAMES.get(req.locale.lower()[:2], "the user's language")

    try:
        result = await retrieve(req.question, as_of=req.as_of)
    except (DependencyUnavailable, GraphUnavailable) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "dependency_unavailable", "detail": str(exc)},
        ) from None

    async def event_stream():
        meta = {
            "query_id": query_id,
            "sources": [s.citation_dict() for s in result.sources],
        }
        yield _sse("meta", meta)

        finish = "complete"
        answer_text = ""

        passages = [(s.n, s.label, s.text) for s in result.sources] if result.sources else []
        context = (
            build_context_block(passages)
            if passages
            else "No specific local by-law excerpt found in the database for this query."
        )
        messages = [
            llm.Message("system", build_system("the municipality", language)),
            *(llm.Message(t.role, t.content) for t in req.history),
            llm.Message(
                "user",
                f"{context}\n\nQUESTION: {req.question}\n\nAnswer following your rules.",
            ),
        ]
        try:
            chunks: list[str] = []
            async for token in llm.stream_chat(messages):
                chunks.append(token)
                yield _sse("token", {"text": token})
            raw_answer = "".join(chunks)
            cleaned, used = (
                validate_citations(raw_answer, len(result.sources))
                if result.sources
                else (raw_answer, [])
            )
            answer_text = cleaned

            if used:
                used_sources = [s for s in result.sources if s.n in used]
                yield _sse(
                    "citations",
                    {
                        "used": used,
                        "sources": [s.citation_dict() for s in used_sources],
                    },
                )
            else:
                yield _sse("citations", {"used": [], "sources": []})
        except llm.LLMError:
            yield _sse("notice", {"text": DEGRADED_NOTICE, "kind": "generation_unavailable"})
            finish = "degraded"

        latency_ms = int((time.perf_counter() - started) * 1000)
        yield _sse("done", {"finish": finish, "latency_ms": latency_ms})

        await graph.audit(
            {
                "query_id": query_id,
                "question": req.question,
                "locale": req.locale,
                "as_of": req.as_of.isoformat() if req.as_of else None,
                "finish": finish,
                "n_sources": len(result.sources),
                "best_dense": round(result.best_dense, 4),
                "answer_chars": len(answer_text),
                "latency_ms": latency_ms,
                "at": Date.today().isoformat(),
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
