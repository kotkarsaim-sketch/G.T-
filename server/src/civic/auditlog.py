"""Audit-trail queries shared by the admin API and the audit CLI."""

from civic import graph


async def recent(n: int) -> list[dict]:
    return await graph.read(
        """
        MATCH (a:AuditEntry)
        RETURN a.at AS at, a.query_id AS query_id, a.question AS question,
               a.finish AS finish, a.latency_ms AS latency_ms,
               a.n_sources AS n_sources, a.locale AS locale, a.as_of AS as_of
        ORDER BY a.at DESC LIMIT $n
        """,
        {"n": n},
    )


async def stats() -> dict:
    rows = await graph.read(
        "MATCH (a:AuditEntry) RETURN a.finish AS finish, a.latency_ms AS latency_ms"
    )
    by_finish: dict[str, int] = {}
    latencies: list[int] = []
    for r in rows:
        by_finish[r["finish"]] = by_finish.get(r["finish"], 0) + 1
        if r["latency_ms"] is not None:
            latencies.append(r["latency_ms"])
    latencies.sort()

    def pct(q: float) -> int | None:
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(q * len(latencies)))]

    return {
        "total": len(rows),
        "by_finish": by_finish,
        "latency_ms": {"p50": pct(0.5), "p95": pct(0.95)},
    }


async def one(query_id: str) -> dict | None:
    rows = await graph.read(
        "MATCH (a:AuditEntry {query_id: $qid}) RETURN a AS record LIMIT 1",
        {"qid": query_id},
    )
    return rows[0]["record"] if rows else None
