"""Public read endpoints over instruments and articles (api-spec §2.3–2.5)."""

from fastapi import APIRouter, HTTPException, Query

from civic import graph
from civic.graph import GraphUnavailable

router = APIRouter(tags=["instruments"])


def _unavailable(exc: GraphUnavailable) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "dependency_unavailable", "detail": str(exc)},
    )


@router.get("/instruments")
async def list_instruments(
    kind: str | None = None,
    status: str = "in_force",
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    clauses = ["1 = 1"]
    params: dict = {"limit": limit}
    if status != "any":
        clauses.append("i.status = $status")
        params["status"] = status
    if kind:
        clauses.append("i.kind = $kind")
        params["kind"] = kind
    if q:
        clauses.append("toLower(i.title) CONTAINS toLower($q)")
        params["q"] = q
    where = " AND ".join(clauses)
    try:
        rows = await graph.read(
            f"""
            MATCH (i:Instrument)
            WHERE {where}
            RETURN i.id AS id, i.kind AS kind, i.number AS number, i.title AS title,
                   i.status AS status, i.effective_from AS effective_from,
                   i.effective_to AS effective_to, i.source_url AS source_url,
                   i.language AS language
            ORDER BY i.effective_from DESC
            LIMIT $limit
            """,
            params,
        )
    except GraphUnavailable as exc:
        raise _unavailable(exc) from None
    return {"items": rows, "next_cursor": None}


@router.get("/instruments/{instrument_id}")
async def get_instrument(instrument_id: str) -> dict:
    try:
        rows = await graph.read(
            """
            MATCH (i:Instrument {id: $id})
            OPTIONAL MATCH (a:Article)-[:PART_OF]->(i)
            WITH i, a ORDER BY a.ordinal
            RETURN i.id AS id, i.kind AS kind, i.number AS number, i.title AS title,
                   i.status AS status, i.enacted_on AS enacted_on,
                   i.effective_from AS effective_from, i.effective_to AS effective_to,
                   i.source_url AS source_url, i.language AS language,
                   collect(CASE WHEN a IS NULL THEN null ELSE {
                       id: a.id, number: a.number, heading: a.heading
                   } END) AS articles
            """,
            {"id": instrument_id},
        )
    except GraphUnavailable as exc:
        raise _unavailable(exc) from None
    if not rows:
        raise HTTPException(status_code=404, detail="instrument not found")
    instrument = rows[0]
    instrument["articles"] = [a for a in instrument["articles"] if a]
    return instrument


@router.get("/articles/{article_id}")
async def get_article(article_id: str) -> dict:
    try:
        rows = await graph.read(
            """
            MATCH (a:Article {id: $id})-[:PART_OF]->(i:Instrument)
            OPTIONAL MATCH (a)-[:REFERENCES]->(r:Article)-[:PART_OF]->(ri:Instrument)
            OPTIONAL MATCH (back:Article)-[:REFERENCES]->(a)
            RETURN a.id AS id, a.number AS number, a.heading AS heading,
                   a.body_text AS body_text,
                   {id: i.id, number: i.number, title: i.title, status: i.status} AS instrument,
                   collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE {
                       id: r.id, number: r.number, heading: r.heading,
                       instrument_number: ri.number
                   } END) AS references_out,
                   collect(DISTINCT CASE WHEN back IS NULL THEN null ELSE {
                       id: back.id, number: back.number
                   } END) AS references_in
            """,
            {"id": article_id},
        )
    except GraphUnavailable as exc:
        raise _unavailable(exc) from None
    if not rows:
        raise HTTPException(status_code=404, detail="article not found")
    article = rows[0]
    article["references_out"] = [r for r in article["references_out"] if r]
    article["references_in"] = [r for r in article["references_in"] if r]
    return article
