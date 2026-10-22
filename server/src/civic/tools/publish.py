"""Publish instruments that are waiting in the amendment review gate.

Usage:
    python -m civic.tools.publish --list
    python -m civic.tools.publish --number 2025-031 [--effective-on 2026-08-26]
"""

import argparse
import sys
from datetime import date

from civic import review


def main() -> None:
    parser = argparse.ArgumentParser(description="Amendment review gate")
    parser.add_argument("--list", action="store_true", help="list pending instruments")
    parser.add_argument("--number", help="instrument number to publish")
    parser.add_argument("--effective-on", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    import asyncio

    if args.list:
        rows = asyncio.run(review.list_pending())
        if not rows:
            print("nothing pending review")
            return
        for r in rows:
            amendments = ", ".join(a for a in (r.get("pending_amendments") or []) if a) or "-"
            print(f"  {r['number']}  {r['title']}  (enacted {r['enacted_on']}, amendments: {amendments})")
    elif args.number:
        try:
            result = asyncio.run(review.publish(args.number, args.effective_on or date.today()))
        except LookupError as exc:
            sys.exit(f"error: {exc}")
        print(f"published {result['id']}: {result['title']} (in force {(args.effective_on or date.today()).isoformat()})")
    else:
        parser.print_help(sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
