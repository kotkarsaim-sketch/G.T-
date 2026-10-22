"""Operator CLI over the audit trail (operations runbook RB-4).

Usage:
    python -m civic.tools.audit --last 20          # recent queries
    python -m civic.tools.audit --stats            # refusal rate, latency profile
    python -m civic.tools.audit --query-id q_ab12  # one full record
"""

import argparse
import sys

from civic import auditlog


def _fmt_ms(v) -> str:
    return f"{int(v)}ms" if v is not None else "-"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit trail inspector")
    parser.add_argument("--last", type=int, default=None, metavar="N")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--query-id", default=None)
    args = parser.parse_args()

    import asyncio

    if args.query_id:
        record = asyncio.run(auditlog.one(args.query_id))
        if record is None:
            sys.exit(f"error: no audit record for {args.query_id}")
        for key, value in record.items():
            print(f"  {key:<14}: {value}")
    elif args.stats:
        async def run() -> None:
            s = await auditlog.stats()
            print(f"total sessions : {s['total']}")
            for finish, n in sorted(s["by_finish"].items()):
                print(f"  {finish:<10} : {n:>5}  ({n / s['total']:.0%})")
            lat = s["latency_ms"]
            print(f"latency p50/p95: {_fmt_ms(lat['p50'])} / {_fmt_ms(lat['p95'])}")

        asyncio.run(run())
    else:
        async def run() -> None:
            rows = await auditlog.recent(args.last or 20)
            if not rows:
                print("audit trail is empty")
                return
            print(f"{'when':<12} {'query_id':<16} {'finish':<10} {'lat':>7} {'src':>4}  question")
            print("-" * 100)
            for r in rows:
                q = (r["question"] or "")[:52]
                print(
                    f"{str(r['at'])[:10]:<12} {r['query_id']:<16} {r['finish']:<10} "
                    f"{_fmt_ms(r['latency_ms']):>7} {r['n_sources'] or 0:>4}  {q}"
                )

        asyncio.run(run())


if __name__ == "__main__":
    main()
