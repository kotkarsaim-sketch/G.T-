"""Review-queue operations shared by the admin API and the publish CLI."""

import logging
from datetime import date

from civic import graph

log = logging.getLogger(__name__)


async def list_pending() -> list[dict]:
    return await graph.read(
        """
        MATCH (i:Instrument {status: 'pending_review'})
        OPTIONAL MATCH (m:Amendment {status: 'pending_review'})-[:AMENDS]->(i)
        RETURN i.id AS id, i.number AS number, i.title AS title,
               i.enacted_on AS enacted_on, i.kind AS kind,
               collect(m.id)[..3] AS pending_amendments
        ORDER BY i.number
        """
    )


async def publish(number: str, effective_on: date) -> dict:
    """Flip a pending_review instrument to in_force. Raises LookupError if absent."""
    rows = await graph.write(
        """
        MATCH (i:Instrument {number: $number, status: 'pending_review'})
        SET i.status = 'in_force', i.effective_from = date($effective)
        RETURN i.id AS id, i.title AS title
        """,
        {"number": number, "effective": effective_on.isoformat()},
    )
    if not rows:
        raise LookupError(f"no instrument with number {number} in pending_review")

    await graph.write(
        """
        MATCH (m:Amendment {status: 'pending_review'})-[:AMENDS]->(:Instrument {number: $number})
        SET m.status = 'published', m.effective_on = date($effective)
        """,
        {"number": number, "effective": effective_on.isoformat()},
    )
    log.info("published %s (%s) effective %s", rows[0]["id"], rows[0]["title"], effective_on)
    return rows[0]
