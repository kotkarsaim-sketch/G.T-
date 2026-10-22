"""Hybrid retrieval pipeline (retrieval design doc §3–§6).

Three candidate channels (dense, lexical, structural) -> reciprocal rank
fusion -> graph expansion over the legal ontology -> grounded context pool
with a mechanical evidence gate.
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date as Date

from civic import embeddings, graph
from civic.settings import get_settings

log = logging.getLogger(__name__)


class DependencyUnavailable(RuntimeError):
    """Raised when an upstream retrieval dependency (e.g. embeddings) is down."""

INSTRUMENT_NUM_RE = re.compile(r"\b((?:19|20)\d{2}-\d{1,4})\b")
SECTION_NUM_RE = re.compile(r"\b(?:sections?\s+|ss\.\s*)(\d+(?:\.\d+)*)", re.IGNORECASE)

RRF_K = 60
STRUCTURAL_BONUS = 0.5
SEED_LIMIT = 12
EXPANSION_BUDGET = 4


def _law_predicate(as_of: Date | None) -> str:
    if as_of is None:
        return graph.CURRENT_LAW
    return (
        "(i.status IN ['in_force','repealed','superseded']) "
        f"AND (i.effective_from IS NULL OR i.effective_from <= date('{as_of.isoformat()}')) "
        "AND (i.effective_to IS NULL OR i.effective_to > date("
        f"'{as_of.isoformat()}'))"
    )


_SOURCE_FIELDS = (
    "node.id AS chunk_id, node.text AS text, "
    "a.id AS article_id, a.number AS article_number, a.heading AS article_heading, "
    "i.id AS instrument_id, i.number AS instrument_number, i.title AS instrument_title, "
    "i.source_url AS url"
)


@dataclass
class Source:
    n: int
    chunk_id: str
    text: str
    instrument_id: str
    instrument_number: str
    instrument_title: str
    article_id: str
    article_number: str
    article_heading: str
    url: str | None
    score: float = 0.0
    origin: str = "seed"

    @property
    def label(self) -> str:
        return (
            f"By-law {self.instrument_number}, s. {self.article_number}"
            + (f" - {self.article_heading}" if self.article_heading else "")
        )

    def citation_dict(self) -> dict:
        return {
            "n": self.n,
            "instrument": {
                "id": self.instrument_id,
                "number": self.instrument_number,
                "title": self.instrument_title,
            },
            "article": {
                "id": self.article_id,
                "number": self.article_number,
                "heading": self.article_heading,
            },
            "url": self.url,
            "score": round(self.score, 4),
            "origin": self.origin,
        }


@dataclass
class RetrievalResult:
    sources: list[Source] = field(default_factory=list)
    refused: bool = False
    best_dense: float = 0.0


async def _vector_search(query: str, qvec: list[float], k: int, as_of: Date | None) -> list[dict]:
    cypher = f"""
    CALL db.index.vector.queryNodes('chunk_embedding', $k, $qvec)
    YIELD node, score
    MATCH (a:Article)-[:HAS_CHUNK]->(node)
    MATCH (a)-[:PART_OF]->(i:Instrument)
    WHERE {_law_predicate(as_of)}
    RETURN {_SOURCE_FIELDS}, score AS dense_score
    ORDER BY dense_score DESC LIMIT $k
    """
    return await graph.read(cypher, {"k": k, "qvec": qvec})


async def _fulltext_search(query: str, k: int, as_of: Date | None) -> list[dict]:
    cypher = f"""
    CALL db.index.fulltext.queryNodes('chunk_text', $q, {{limit: $k}})
    YIELD node, score
    MATCH (a:Article)-[:HAS_CHUNK]->(node)
    MATCH (a)-[:PART_OF]->(i:Instrument)
    WHERE {_law_predicate(as_of)}
    RETURN {_SOURCE_FIELDS}
    LIMIT $k
    """
    return await graph.read(cypher, {"q": query, "k": k})


async def _structural_lookup(question: str, as_of: Date | None) -> list[dict]:
    instruments = INSTRUMENT_NUM_RE.findall(question)
    sections = SECTION_NUM_RE.findall(question)
    if not instruments and not sections:
        return []
    rows: list[dict] = []
    where = _law_predicate(as_of)
    if instruments:
        rows.extend(
            await graph.read(
                f"""
                MATCH (i:Instrument {{number: $inst}})
                WHERE {where}
                MATCH (a:Article)-[:PART_OF]->(i)
                MATCH (a)-[:HAS_CHUNK]->(node)
                WITH a, i, node ORDER BY a.ordinal, node.ordinal
                WITH a, i, head(collect(node)) AS first_chunk
                RETURN {_SOURCE_FIELDS.replace('node.', 'first_chunk.')}
                LIMIT 6
                """,
                {"inst": instruments[0]},
            )
        )
    if sections:
        rows.extend(
            await graph.read(
                f"""
                MATCH (a:Article {{number: $sec}})-[:PART_OF]->(i:Instrument)
                WHERE {where}
                MATCH (a)-[:HAS_CHUNK]->(node)
                WITH a, i, node ORDER BY node.ordinal
                WITH a, i, head(collect(node)) AS first_chunk
                RETURN {_SOURCE_FIELDS.replace('node.', 'first_chunk.')}
                LIMIT 6
                """,
                {"sec": sections[0]},
            )
        )
    return rows


async def _expand(seed_ids: list[str], as_of: Date | None) -> list[dict]:
    where = _law_predicate(as_of)
    siblings = await graph.read(
        f"""
        UNWIND $ids AS cid
        MATCH (c:Chunk {{id: cid}})<-[:HAS_CHUNK]-(a:Article)-[:PART_OF]->(i:Instrument)
        WHERE {where}
        WITH a, i, [(a)-[:HAS_CHUNK]->(s) WHERE s.id <> cid | s][..2] AS sibs
        UNWIND sibs AS node
        WITH DISTINCT node, a, i
        RETURN {_SOURCE_FIELDS}
        LIMIT 8
        """,
        {"ids": seed_ids},
    )
    references = await graph.read(
        f"""
        UNWIND $ids AS cid
        MATCH (c:Chunk {{id: cid}})<-[:HAS_CHUNK]-(a:Article)-[:REFERENCES]->(r:Article)
        MATCH (r)-[:PART_OF]->(i:Instrument)
        WHERE {where}
        MATCH (r)-[:HAS_CHUNK]->(node)
        WITH r, i, node ORDER BY node.ordinal
        WITH r, i, head(collect(node)) AS node
        RETURN {_SOURCE_FIELDS.replace('a.', 'r.')}
        LIMIT 8
        """,
        {"ids": seed_ids},
    )
    return [(row, "sibling") for row in siblings] + [(row, "reference") for row in references]


async def retrieve(
    question: str,
    as_of: Date | None = None,
) -> RetrievalResult:
    """Full hybrid retrieval with expansion and the evidence gate."""
    s = get_settings()
    query = re.sub(r"\s+", " ", question).strip()
    try:
        qvecs = await embeddings.embed([query])
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed 503 upstream
        raise DependencyUnavailable("embedding service unavailable") from exc
    qvec = qvecs[0]

    vec_rows, ft_rows, struct_rows = await asyncio.gather(
        _vector_search(query, qvec, s.retrieval_vector_k, as_of),
        _fulltext_search(query, s.retrieval_fulltext_k, as_of),
        _structural_lookup(query, as_of),
    )

    best_dense = max((float(r.get("dense_score") or 0.0) for r in vec_rows), default=0.0)

    # Reciprocal Rank Fusion across channels; dedupe at chunk level.
    fused: dict[str, dict] = {}
    for rows, bonus in ((vec_rows, 0.0), (ft_rows, 0.0), (struct_rows, STRUCTURAL_BONUS)):
        for rank, row in enumerate(rows):
            cid = row["chunk_id"]
            entry = fused.setdefault(
                cid,
                {"row": row, "rrf": 0.0, "bonus": 0.0},
            )
            entry["rrf"] += 1.0 / (RRF_K + rank + 1)
            entry["bonus"] = max(entry["bonus"], bonus)

    ordered = sorted(
        fused.values(), key=lambda e: e["rrf"] + e["bonus"], reverse=True
    )[:SEED_LIMIT]

    has_structural = any(e["bonus"] > 0 for e in ordered)
    if not ordered or (best_dense < s.retrieval_min_score and not has_structural):
        return RetrievalResult(refused=True, best_dense=best_dense)

    seed_ids = [e["row"]["chunk_id"] for e in ordered]
    expanded_rows = await _expand(seed_ids, as_of)

    sources: list[Source] = []
    seen: set[str] = set()
    for e in ordered:
        row = e["row"]
        cid = row["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)
        sources.append(_to_source(row, n=len(sources) + 1, score=e["rrf"] + e["bonus"], origin="seed"))
        if len(sources) >= s.retrieval_final_k:
            break

    for row, origin in expanded_rows:
        cid = row["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)
        sources.append(_to_source(row, n=len(sources) + 1, score=0.0, origin=origin))
        if len(sources) >= s.retrieval_final_k + EXPANSION_BUDGET:
            break

    if s.enable_rerank:
        sources = await _apply_rerank(query, sources)

    return RetrievalResult(
        sources=sources,
        refused=False,
        best_dense=best_dense,
    )


def _to_source(row: dict, n: int, score: float, origin: str) -> Source:
    return Source(
        n=n,
        chunk_id=row["chunk_id"],
        text=row["text"],
        instrument_id=row["instrument_id"],
        instrument_number=row["instrument_number"] or "",
        instrument_title=row["instrument_title"] or "",
        article_id=row["article_id"],
        article_number=row["article_number"] or "?",
        article_heading=row["article_heading"] or "",
        url=row.get("url"),
        score=score,
        origin=origin,
    )


async def _apply_rerank(query: str, sources: list[Source]) -> list[Source]:
    try:
        ranked = await embeddings.rerank(query, [src.text for src in sources])
    except Exception:  # noqa: BLE001 - reranker is an optimization, never a dependency
        log.warning("rerank unavailable; keeping fusion order")
        return sources
    rescored = sorted(zip(sources, ranked), key=lambda pair: pair[1][1], reverse=True)
    out = [src for src, _ in rescored]
    for i, src in enumerate(out):
        src.n = i + 1
    return out


async def search_only(
    question: str, mode: str = "hybrid", limit: int = 10, as_of: Date | None = None
) -> list[Source]:
    """Retrieval without generation, for the browse view and eval harness."""
    s = get_settings()
    query = re.sub(r"\s+", " ", question).strip()

    if mode == "vector":
        try:
            qvec = (await embeddings.embed([query]))[0]
        except Exception as exc:  # noqa: BLE001
            raise DependencyUnavailable("embedding service unavailable") from exc
        rows = await _vector_search(query, qvec, limit, as_of)
        return [
            _to_source(r, i + 1, float(r.get("dense_score") or 0.0), "vector")
            for i, r in enumerate(rows)
        ]
    if mode == "keyword":
        rows = await _fulltext_search(query, limit, as_of)
        return [_to_source(r, i + 1, 0.0, "keyword") for i, r in enumerate(rows)]

    result = await retrieve(question, as_of=as_of)
    return result.sources[:limit]


def new_query_id() -> str:
    return "q_" + uuid.uuid4().hex[:12]
