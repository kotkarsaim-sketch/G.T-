import asyncio

from civic import graph

RAW = (
    "MATCH (x)-[r:REFERENCES]->(y) "
    "RETURN labels(x) AS lx, x.id AS xid, coalesce(x.number, '') AS xnum, "
    "labels(y) AS ly, y.id AS yid, coalesce(y.number, '') AS ynum"
)


async def main() -> None:
    rows = await graph.read(RAW)
    for r in rows:
        print(r)


asyncio.run(main())
