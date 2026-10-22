-- CivicGraph schema bootstrap.
-- Applied automatically by the API at startup; duplicated here so operators
-- can provision the database before first deploy or rebuild it manually.

CREATE CONSTRAINT jurisdiction_code IF NOT EXISTS
FOR (j:Jurisdiction) REQUIRE j.code IS UNIQUE;

CREATE CONSTRAINT instrument_id IF NOT EXISTS
FOR (i:Instrument) REQUIRE i.id IS UNIQUE;

CREATE CONSTRAINT article_id IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT concept_id IF NOT EXISTS
FOR (k:Concept) REQUIRE k.id IS UNIQUE;

CREATE CONSTRAINT amendment_id IF NOT EXISTS
FOR (m:Amendment) REQUIRE m.id IS UNIQUE;

CREATE INDEX instrument_status IF NOT EXISTS
FOR (i:Instrument) ON (i.status);

CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS
FOR (c:Chunk) ON EACH [c.text];

-- NOTE: dimension must match EMBEDDING_DIM (default 1024 for BAAI/bge-m3).
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON c.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};
