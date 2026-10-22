"""Corpus freshness check (operations runbook RB-1).

Recomputes the content hash of every manifest instrument and compares it with
the graph. Exit code 1 on drift so it can run as a nightly cron/CI job.

Usage:
    python -m civic.tools.freshness --source /data/samples/rivermont
"""

import argparse
import sys
from pathlib import Path

from civic import graph
from civic.tools.ingest import _sha256, load_manifest


async def run(source_dir: Path) -> int:
    manifest = load_manifest(source_dir)
    drift = missing = ok = 0

    for entry in manifest.get("instruments") or []:
        instrument_id = entry["id"]
        file_path = source_dir / entry["file"]
        if not file_path.exists():
            print(f"  MISSING   {instrument_id} ({entry['file']} not found)")
            missing += 1
            continue
        current = _sha256(file_path.read_text(encoding="utf-8", errors="replace"))
        rows = await graph.read(
            "MATCH (i:Instrument {id: $id}) RETURN i.content_hash AS h, i.status AS s",
            {"id": instrument_id},
        )
        if not rows:
            print(f"  NOT INGESTED  {instrument_id}")
            missing += 1
        elif rows[0]["h"] == current:
            print(f"  OK        {instrument_id} [{rows[0]['s']}]")
            ok += 1
        else:
            print(f"  DRIFT     {instrument_id} - source changed since last ingest")
            drift += 1

    total = len(manifest.get("instruments") or [])
    print(f"\nfreshness: {ok} ok, {drift} drifted, {missing} missing of {total}")
    return 1 if drift else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Corpus freshness check (RB-1)")
    parser.add_argument("--source", required=True)
    args = parser.parse_args()

    import asyncio

    code = asyncio.run(run(Path(args.source)))
    sys.exit(code)


if __name__ == "__main__":
    main()
