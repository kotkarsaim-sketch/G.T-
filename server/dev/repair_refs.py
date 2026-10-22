import asyncio

from civic import graph

FIND = (
    "MATCH (x)-[r:REFERENCES]->() "
    "WHERE size(labels(x)) = 0 OR x.id IS NULL "
    "RETURN count(r) AS broken"
)
DELETE_BROKEN = (
    "MATCH (x)-[r:REFERENCES]->() "
    "WHERE size(labels(x)) = 0 OR x.id IS NULL "
    "DELETE r"
)
UNLABELED = "MATCH (n) WHERE size(labels(n)) = 0 RETURN count(n) AS n"


async def main() -> None:
    before = await graph.read(FIND)
    print("broken REFERENCES:", before[0]["broken"])
    await graph.write(DELETE_BROKEN)
    stray = await graph.read("MATCH (x) WHERE size(labels(x)) = 0 DETACH DELETE x RETURN count(x) AS n")
    print("unlabeled nodes removed:", stray[0]["n"])
    total = await graph.read("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS n")
    print("clean REFERENCES remaining:", total[0]["n"])


asyncio.run(main())
