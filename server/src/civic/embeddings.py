"""Embedding client for TEI (text-embeddings-inference) compatible servers."""

import asyncio
from typing import Any

import httpx

from civic.settings import get_settings


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    s = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{s.embedding_base_url}/embed",
            json={"inputs": texts, "truncate": True},
        )
        resp.raise_for_status()
        vectors = resp.json()
    dim = s.embedding_dim
    return [v[:dim] for v in vectors]


async def rerank(query: str, texts: list[str]) -> list[tuple[int, float]]:
    """Return [(original_index, score)] sorted desc. Requires TEI /rerank route."""
    s = get_settings()
    if not s.reranker_base_url:
        return [(i, 0.0) for i in range(len(texts))]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{s.reranker_base_url}/rerank",
            json={"query": query, "texts": texts, "raw_scores": False},
        )
        resp.raise_for_status()
        payload: list[dict[str, Any]] = resp.json()
    ranked = sorted(payload, key=lambda d: d["score"], reverse=True)
    return [(int(d["index"]), float(d["score"])) for d in ranked]


async def healthy() -> bool:
    try:
        s = get_settings()
        async with httpx.AsyncClient(timeout=5.0) as client:
            for path in ("/health", "/"):
                try:
                    resp = await client.get(s.embedding_base_url + path)
                    if resp.status_code < 500:
                        return True
                except httpx.HTTPError:
                    continue
        return False
    except Exception:  # noqa: BLE001
        return False


async def embed_batched(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        out.extend(await embed(texts[i : i + batch_size]))
        await asyncio.sleep(0)  # yield to loop between batches
    return out
