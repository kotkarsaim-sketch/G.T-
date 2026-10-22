"""Neo4j access: driver lifecycle, idempotent schema bootstrap, audit writes."""

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from civic.settings import get_settings

log = logging.getLogger(__name__)


class GraphUnavailable(RuntimeError):
    """Raised when Neo4j cannot be reached or the session dies mid-query."""


def _normalize(value: Any) -> Any:
    """Convert driver-native types (notably neo4j.time.*) to JSON-safe values."""
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    iso = getattr(value, "iso_format", None)  # neo4j.time.Date/DateTime/Time/Duration
    if callable(iso):
        return iso()
    isoformat = getattr(value, "isoformat", None)  # stdlib date/time fallbacks
    if callable(isoformat):
        return isoformat()
    return value


def _normalize_rows(rows: list[dict]) -> list[dict]:
    return [_normalize(row) for row in rows]

_driver: AsyncDriver | None = None


def driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = AsyncGraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
            # Schema-exploration notifications (missing rel types on OPTIONAL
            # MATCH, null elimination in collect) are noise for operator CLIs.
            notifications_min_severity="OFF",
        )
    return _driver


async def close() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


CURRENT_LAW = (
    "(i.status = 'in_force') "
    "AND (i.effective_from IS NULL OR i.effective_from <= date()) "
    "AND (i.effective_to IS NULL OR i.effective_to > date())"
)


async def ensure_schema() -> None:
    """Create constraints and indexes if missing. Safe to call on every boot."""
    s = get_settings()
    dim = int(s.embedding_dim)
    statements = [
        "CREATE CONSTRAINT jurisdiction_code IF NOT EXISTS "
        "FOR (j:Jurisdiction) REQUIRE j.code IS UNIQUE",
        "CREATE CONSTRAINT instrument_id IF NOT EXISTS "
        "FOR (i:Instrument) REQUIRE i.id IS UNIQUE",
        "CREATE CONSTRAINT article_id IF NOT EXISTS "
        "FOR (a:Article) REQUIRE a.id IS UNIQUE",
        "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (k:Concept) REQUIRE k.id IS UNIQUE",
        "CREATE CONSTRAINT amendment_id IF NOT EXISTS "
        "FOR (m:Amendment) REQUIRE m.id IS UNIQUE",
        "CREATE INDEX instrument_status IF NOT EXISTS FOR (i:Instrument) ON (i.status)",
        "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
        (
            "CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS "
            "FOR (c:Chunk) ON c.embedding "
            "OPTIONS {indexConfig: {"
            "`vector.dimensions`: %d, `vector.similarity_function`: 'cosine'}}" % dim
        ),
    ]
    async with driver().session(database=s.neo4j_database) as session:
        for stmt in statements:
            await session.run(stmt)
    log.info("schema ensured (embedding dim=%d)", dim)


async def read(cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
    s = get_settings()
    try:
        async with driver().session(database=s.neo4j_database) as session:
            result = await session.run(cypher, params or {})
            return _normalize_rows([record.data() async for record in result])
    except (ServiceUnavailable, SessionExpired) as exc:
        raise GraphUnavailable("graph database unavailable") from exc


async def _write_unit(tx, cypher: str, params: dict[str, Any]) -> list[dict]:
    # Results must be materialized inside the managed transaction; consuming
    # the handle after execute_write returns raises "out of scope".
    result = await tx.run(cypher, params)
    return _normalize_rows([record.data() async for record in result])


async def write(cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
    s = get_settings()
    try:
        async with driver().session(database=s.neo4j_database) as session:
            return await session.execute_write(
                _write_unit, cypher, params or {}
            )
    except (ServiceUnavailable, SessionExpired) as exc:
        raise GraphUnavailable("graph database unavailable") from exc


async def audit(record: dict[str, Any]) -> None:
    """Append-only audit trail. Never blocks or fails the caller."""
    try:
        await write(
            "CREATE (:AuditEntry $record)",
            {"record": record},
        )
    except Exception:  # noqa: BLE001 - audit must never break the response path
        log.exception("audit write failed")
