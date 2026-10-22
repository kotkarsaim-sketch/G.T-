"""Load municipal instruments into the graph.

Usage:
    python -m civic.tools.ingest --source /data/samples/rivermont [--dry-run]
    python -m civic.tools.ingest --re-embed        # re-embed existing chunks

Expected layout: manifest.yaml plus one text/html-ish file per instrument.
Writes are idempotent: stable IDs derived from jurisdiction/instrument/article
plus content hashing mean re-runs converge instead of duplicating.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

from civic import embeddings, graph
from civic.chunking import chunk_article, estimate_tokens, split_articles
from civic.settings import get_settings


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "x"


def _sha256(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()


def load_manifest(source_dir: Path) -> dict:
    manifest_path = source_dir / "manifest.yaml"
    if not manifest_path.exists():
        sys.exit(f"error: {manifest_path} not found")
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))


def prepare_instrument(entry: dict, source_dir: Path) -> dict:
    text_file = source_dir / entry["file"]
    raw = text_file.read_text(encoding="utf-8", errors="replace")
    pattern = entry.get("article_pattern")
    articles = split_articles(raw, pattern)

    prepared_articles = []
    for ordinal, art in enumerate(articles):
        article_id = f"{entry['id']}#s-{_slug(art.number)}"
        texts = chunk_article(art)
        chunks = []
        for ci, text in enumerate(texts):
            chunks.append(
                {
                    "id": f"{article_id}#c-{ci}",
                    "text": text,
                    "tokens": estimate_tokens(text),
                    "ordinal": ci,
                }
            )
        body = "\n\n".join(art.paragraphs)
        prepared_articles.append(
            {
                "id": article_id,
                "number": art.number,
                "heading": art.heading,
                "body": body,
                "ordinal": ordinal,
                "chunks": chunks,
            }
        )
    return {"entry": entry, "raw": raw, "articles": prepared_articles}


async def write_instrument(manifest: dict, prepared: dict) -> None:
    entry = prepared["entry"]
    jur = manifest.get("jurisdiction", {})

    await graph.write(
        """
        MERGE (j:Jurisdiction {code: $jcode})
        ON CREATE SET j.name = $jname, j.level = 'municipal'
        """,
        {"jcode": jur["code"], "jname": jur.get("name", jur["code"])},
    )
    await graph.write(
        """
        MATCH (j:Jurisdiction {code: $jcode})
        MERGE (i:Instrument {id: $id})
        SET i.kind = $kind,
            i.number = $number,
            i.title = $title,
            i.status = $status,
            i.source_url = $url,
            i.language = $language,
            i.content_hash = $hash,
            i.effective_from = CASE WHEN $eff_from IS NULL THEN i.effective_from ELSE date($eff_from) END,
            i.effective_to = CASE WHEN $eff_to IS NULL THEN null ELSE date($eff_to) END,
            i.enacted_on = CASE WHEN $enacted IS NULL THEN i.enacted_on ELSE date($enacted) END
        MERGE (i)-[:ENACTED_BY]->(j)
        """,
        {
            "jcode": jur["code"],
            "id": entry["id"],
            "kind": entry.get("kind", "bylaw"),
            "number": str(entry.get("number", "")),
            "title": entry["title"],
            "status": entry.get("status", "in_force"),
            "url": entry.get("source_url"),
            "language": entry.get("language", "en"),
            "hash": _sha256(prepared["raw"]),
            "eff_from": entry.get("effective_from"),
            "eff_to": entry.get("effective_to"),
            "enacted": entry.get("enacted_on"),
        },
    )
    # Replace all chunks for this instrument atomically, then recreate.
    await graph.write(
        """
        MATCH (i:Instrument {id: $id})
        OPTIONAL MATCH (a:Article)-[hc:HAS_CHUNK]->(c:Chunk)
        WHERE (a)-[:PART_OF]->(i)
        DELETE hc, c
        """,
        {"id": entry["id"]},
    )
    await graph.write(
        """
        MATCH (i:Instrument {id: $id})
        UNWIND $articles AS art
        MERGE (a:Article {id: art.id})
        SET a.number = art.number, a.heading = art.heading,
            a.body_text = art.body, a.ordinal = art.ordinal
        MERGE (a)-[:PART_OF]->(i)
        WITH a, art
        UNWIND art.chunks AS ch
        CREATE (c:Chunk {id: ch.id})
        SET c.text = ch.text, c.token_estimate = ch.tokens, c.ordinal = ch.ordinal,
            c.embedding = ch.vec
        MERGE (a)-[:HAS_CHUNK]->(c)
        """,
        {"id": entry["id"], "articles": prepared["articles"]},
    )


async def write_cross_references(manifest: dict) -> int:
    """Load clerk-curated cross-references declared in the manifest."""
    refs = manifest.get("cross_references") or []
    resolved = 0
    for ref in refs:
        rows = await graph.write(
            """
            MATCH (:Instrument {number: $fi})<-[:PART_OF]-(src:Article {number: $fa})
            MATCH (:Instrument {number: $ti})<-[:PART_OF]-(dst:Article {number: $ta})
            MERGE (src)-[:REFERENCES]->(dst)
            RETURN src.id AS src_id, dst.id AS dst_id
            """,
            {
                "fi": str(ref["from_instrument"]),
                "fa": str(ref["from_article"]),
                "ti": str(ref["to_instrument"]),
                "ta": str(ref["to_article"]),
            },
        )
        if rows:
            resolved += 1
            print(f"  cross-ref {rows[0]['src_id']} -> {rows[0]['dst_id']}")
        else:
            print(f"  UNRESOLVED cross-ref: {ref}", file=sys.stderr)
    return resolved


async def re_embed_all() -> None:
    """Re-embed every existing chunk with the current embedding model.

    Handles the ADR-001 caveat: if the configured dimension differs from the
    vector index, the index is dropped and recreated before writing.
    """
    s = get_settings()
    rows = await graph.read("MATCH (c:Chunk) RETURN c.id AS id, c.text AS text ORDER BY c.id")
    if not rows:
        print("no chunks to re-embed")
        return

    idx = await graph.read(
        """
        SHOW INDEXES YIELD name, options
        WHERE name = 'chunk_embedding'
        RETURN options.indexConfig['vector.dimensions'] AS dim
        """
    )
    current_dim = idx[0]["dim"] if idx else None
    if current_dim is not None and current_dim != s.embedding_dim:
        await graph.write("DROP INDEX chunk_embedding")
        await graph.ensure_schema()
        print(f"vector index rebuilt for dim {s.embedding_dim} (was {current_dim})")
    elif current_dim is None:
        await graph.ensure_schema()

    texts = [r["text"] for r in rows]
    vectors = await embeddings.embed_batched(texts)

    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = [
            {"id": rows[j]["id"], "vec": vectors[j]}
            for j in range(i, min(i + batch_size, len(rows)))
        ]
        await graph.write(
            "UNWIND $batch AS b MATCH (c:Chunk {id: b.id}) SET c.embedding = b.vec",
            {"batch": batch},
        )
    print(f"re-embedded {len(rows)} chunks at dim {s.embedding_dim} ({s.embedding_model})")


async def run(source_dir: Path, dry_run: bool) -> None:
    manifest = load_manifest(source_dir)
    entries = manifest.get("instruments") or []
    if not entries:
        sys.exit("error: manifest lists no instruments")

    total_articles = total_chunks = 0
    failures: list[str] = []

    for entry in entries:
        try:
            prepared = prepare_instrument(entry, source_dir)
            n_chunks = sum(len(a["chunks"]) for a in prepared["articles"])
            total_articles += len(prepared["articles"])
            total_chunks += n_chunks
            print(
                f"  parsed {entry['id']}: {len(prepared['articles'])} articles, "
                f"{n_chunks} chunks"
            )

            if dry_run:
                continue

            texts = [ch["text"] for a in prepared["articles"] for ch in a["chunks"]]
            vectors = await embeddings.embed_batched(texts)
            idx = 0
            for article in prepared["articles"]:
                for ch in article["chunks"]:
                    ch["vec"] = vectors[idx]
                    idx += 1
            await write_instrument(manifest, prepared)
        except Exception as exc:  # noqa: BLE001 - report every instrument independently
            failures.append(entry["id"])
            print(f"  FAILED {entry['id']}: {exc}", file=sys.stderr)

    mode = "DRY RUN" if dry_run else "written"
    print(f"\ningest {mode}: {total_articles} articles, {total_chunks} chunks")

    if not dry_run and not failures:
        n = await write_cross_references(manifest)
        print(f"curated cross-references: {n}/{len(manifest.get('cross_references') or [])}")

    if failures:
        print(f"failures: {json.dumps(failures)}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="CivicGraph corpus ingestion")
    parser.add_argument("--source", default=None, help="directory containing manifest.yaml")
    parser.add_argument("--dry-run", action="store_true", help="parse and report only")
    parser.add_argument(
        "--re-embed",
        action="store_true",
        help="re-embed existing chunks with the current model (no reparse)",
    )
    args = parser.parse_args()

    import asyncio

    if args.re_embed:
        asyncio.run(re_embed_all())
        return

    if not args.source:
        parser.error("--source is required unless --re-embed is given")
    asyncio.run(run(Path(args.source), args.dry_run))


if __name__ == "__main__":
    main()
