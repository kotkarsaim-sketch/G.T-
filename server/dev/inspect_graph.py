import asyncio

from civic import graph

EDGES = "MATCH (a:Article)-[r:REFERENCES]->(b:Article) RETURN a.id AS src, b.id AS dst ORDER BY src"
COUNT = "MATCH (:Article {id: $aid}) RETURN count(*) AS c"
TYPES = "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY n DESC"


async def main() -> None:
    types = await graph.read(TYPES)
    print("rel types:", [(x["t"], x["n"]) for x in types])

    aid = "rivermont-bylaw-2023-047#s-4"
    exists = await graph.read(COUNT, {"aid": aid})
    print(f"article {aid} exists:", exists[0]["c"])

    edges = await graph.read(EDGES)
    print(f"REFERENCES edges ({len(edges)}):")
    for e in edges:
        print(f"  {e['src']} -> {e['dst']}")


asyncio.run(main())
