# ADR-001 · Neo4j as unified graph and vector store

Status: Accepted · 2026-07-14
Deciders: Platform team; ratified by IT Architecture Board

## Context

The core asset is the legal ontology — instruments, articles, amendments,
cross-references — and retrieval needs both similarity search over text chunks
and traversal of that structure in one query path ("find sections like this,
then pull what they reference"). We must choose where the vector index lives.

## Decision

Neo4j 5.x stores the property graph **and** the dense vectors, using its native
vector index (cosine, dimension fixed at index creation). No separate vector
database.

## Rationale

1. Retrieval quality depends on graph expansion immediately after candidate
   generation. One database means one query round-trip and no cross-store ID
   synchronization.
2. Operational surface for a municipal IT department matters more than
   benchmark deltas at our scale (< 100k chunks): one backup procedure, one
   monitoring story, one thing to learn.
3. Fulltext (BM25) indexes are also native, so hybrid retrieval stays in-process.

## Alternatives considered

- **PostgreSQL + pgvector**: strong default for many projects; we would end up
  writing recursive CTEs to do what Cypher expresses directly, and reference
  graphs would live awkwardly beside relational rows. Revisit if reporting
  requirements grow heavy.
- **Dedicated vector DB (Qdrant, Pinecone) beside Neo4j**: adds a sync problem
  on every re-ingest and a second failure domain for marginal gain at this
  corpus size.
- **In-memory FAISS in the API**: fastest option, but loses persistence,
  filtering, and multi-client consistency; a non-starter for an audited system.

## Consequences

Positive: single transactional write path; expansion queries read consistent
state; ops simplicity as above.

Negative / accepted: vector index dimension is baked in — changing embedding
models requires a rebuild pass (`ingest --rebuild-vectors`); Neo4j's vector
index lacks some specialized ANN features (metadata-filtered HNSW tuning) that
we do not currently need; Enterprise features (causal clustering) carry license
cost if HA demands them later.
