"""Enrich articles with cross-references and concept links using the LLM.

Usage:
    python -m civic.tools.enrich [--limit 100] [--propose-concepts]

Only validated relationships reach the graph. Unresolvable references are
counted, never guessed at. Concept labels become live :Concept nodes only when
run without --propose-concepts (librarian review path).
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError

from civic import graph, llm
from civic.prompts import EXTRACTION_SYSTEM


class RefItem(BaseModel):
    instrument_number: str = ""
    article_number: str


class Extracted(BaseModel):
    references: list[RefItem] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


def _slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "x"


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.+?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


async def fetch_pending(limit: int) -> list[dict]:
    return await graph.read(
        """
        MATCH (a:Article)-[:PART_OF]->(i:Instrument)
        WHERE i.status = 'in_force' AND a.enriched_at IS NULL
              AND size(a.body_text) > 40
        RETURN a.id AS id, a.number AS number, a.heading AS heading,
               a.body_text AS body, i.number AS instrument_number
        ORDER BY a.id LIMIT $limit
        """,
        {"limit": limit},
    )


async def apply_extraction(article_id: str, extracted: Extracted, propose_concepts: bool) -> tuple[int, int]:
    resolved = unresolved = 0
    for ref in extracted.references:
        rows = await graph.write(
            """
            MATCH (src:Article {id: $src})
            MATCH (ti:Instrument)
            WHERE ti.status = 'in_force'
              AND ($inst = '' OR ti.number = $inst)
            MATCH (t:Article {number: $sec})-[:PART_OF]->(ti)
            WHERE t.id <> $src
            WITH t LIMIT 1
            MERGE (src)-[:REFERENCES]->(t)
            RETURN t.id AS target
            """,
            {"src": article_id, "inst": ref.instrument_number.strip(), "sec": ref.article_number},
        )
        if rows:
            resolved += 1
        else:
            unresolved += 1

    for label in extracted.concepts[:4]:
        clean = label.strip().lower()
        if not clean or len(clean) > 60:
            continue
        cid = _slugify(clean)
        if propose_concepts:
            await graph.write(
                """
                MERGE (p:ConceptProposal {id: $cid})
                ON CREATE SET p.label = $label, p.proposed_by = $src
                """,
                {"cid": cid, "label": clean, "src": article_id},
            )
        else:
            await graph.write(
                """
                MERGE (k:Concept {id: $cid})
                ON CREATE SET k.label = $label
                WITH k
                MATCH (a:Article {id: $src})
                MERGE (a)-[:ABOUT]->(k)
                """,
                {"cid": cid, "label": clean, "src": article_id},
            )
    return resolved, unresolved


async def run(limit: int, propose_concepts: bool) -> None:
    pending = await fetch_pending(limit)
    if not pending:
        print("nothing to enrich")
        return

    resolved_total = unresolved_total = errors = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in pending:
        heading = f"Section {row['number']} - {row['heading']}" if row["heading"] else f"Section {row['number']}"
        user_msg = (
            f"Instrument: by-law {row['instrument_number']}\n"
            f"{heading}\n\n{row['body']}"
        )
        try:
            raw = await llm.complete(
                [
                    llm.Message("system", EXTRACTION_SYSTEM),
                    llm.Message("user", user_msg),
                ]
            )
            extracted = Extracted(**_parse_json(raw))
            resolved, unresolved = await apply_extraction(
                row["id"], extracted, propose_concepts
            )
            resolved_total += resolved
            unresolved_total += unresolved
        except (ValidationError, ValueError, llm.LLMError, json.JSONDecodeError) as exc:
            errors += 1
            print(f"  extraction failed for {row['id']}: {exc}", file=sys.stderr)
            continue

        await graph.write(
            "MATCH (a:Article {id: $id}) SET a.enriched_at = datetime($now)",
            {"id": row["id"], "now": now},
        )

    print(
        f"enrichment done: {len(pending)} articles, "
        f"{resolved_total} references resolved, {unresolved_total} unresolvable, "
        f"{errors} errors"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CivicGraph graph enrichment")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--propose-concepts",
        action="store_true",
        help="stage concept suggestions instead of creating them",
    )
    args = parser.parse_args()
    asyncio.run(run(args.limit, args.propose_concepts))


if __name__ == "__main__":
    main()
