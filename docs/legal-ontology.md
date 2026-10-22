# CivicGraph Legal Ontology

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) |
| Scope | Property graph schema for municipal legal instruments |

---

## 1. Modeling stance

The schema models **what the clerk's office publishes**, not legal theory.
Every node maps to something a resident could be pointed to: a by-law, a
section, an amendment record. We keep legal-theoretic constructs (norms,
deontic operators like obligations/prohibitions as first-class nodes) out of
phase 1 — extraction of those reliably requires counsel review, and mislabeled
obligations are worse than none. The `Concept` layer provides the topical glue
instead.

Two properties drive most of the system's trust story:

- **Temporal validity** on every instrument and amendment (`effective_from`,
  `effective_to`, `status`), so "current law" is a query, not an assumption.
- **Stable content-hashed IDs**, so re-ingesting a corrected PDF updates text
  without duplicating history or breaking stored citations.

## 2. Node types

### Jurisdiction

The enacting authority. One per deployment in phase 1, modeled anyway so the
graph survives consolidation projects.

```cypher
(:Jurisdiction {
  code: STRING,          -- 'rivermont', unique
  name: STRING,          -- 'City of Rivermont'
  level: STRING          -- 'municipal'
})
```

### Instrument

Any published legal document: by-law, ordinance, resolution, council policy.

```cypher
(:Instrument {
  id: STRING,            -- '{jurisdiction}-{kind}-{number}', e.g. rivermont-bylaw-2024-112
  kind: STRING,          -- bylaw | ordinance | resolution | policy
  number: STRING,        -- '2024-112' (display form)
  title: STRING,
  status: STRING,        -- draft | pending_review | in_force | repealed | superseded
  enacted_on: DATE,
  effective_from: DATE,
  effective_to: DATE,    -- null while in force
  source_url: STRING,    -- canonical clerk URL, used for citation deep links
  language: STRING,      -- BCP-47 of the source text
  content_hash: STRING   -- sha256 of normalized full text; change detection
})
```

### Article

A numbered section (or unnumbered preamble/schedule item) of an instrument.

```cypher
(:Article {
  id: STRING,            -- '{instrument_id}#s-{number}'
  number: STRING,        -- '3', '3.1', 'Preamble', 'Schedule A-2'
  heading: STRING,       -- 'Noise limits in residential zones'
  body_text: STRING,     -- full section text (chunking happens downstream)
  ordinal: INTEGER       -- position within instrument, for ordering
})
```

### Chunk

Retrieval unit. Articles longer than ~350 tokens split into ordered chunks;
chunks never straddle articles (ADR-004).

```cypher
(:Chunk {
  id: STRING,            -- '{article_id}#c-{ordinal}'
  text: STRING,
  embedding: LIST<FLOAT>,-- dim per config (default 1024)
  token_estimate: INTEGER,
  ordinal: INTEGER,
  enriched_at: DATETIME  -- null until enrichment pass has processed it
})
```

### Concept

Topical label linking articles across instruments ('short-term rental',
'noise', 'home occupation'). Slugs are curated; the enrichment step may only
attach existing concepts unless run in `--propose-concepts` mode, which writes
`(:ConceptProposal)` nodes for librarian review instead of live nodes.

```cypher
(:Concept {
  id: STRING,            -- slug
  label: STRING,
  language: STRING,
  broader_id: STRING     -- optional parent slug for a light SKOS-style tree
})
```

### Amendment

A dated change event between instruments. Kept as a node (not just properties)
because amendments carry narrative the clerk needs: summaries, motion numbers,
point-in-time answers ("what changed in June 2024?").

```cypher
(:Amendment {
  id: STRING,
  change_summary: STRING,
  approved_on: DATE,
  effective_on: DATE,
  status: STRING,        -- pending_review | published
  motion_ref: STRING
})
```

## 3. Relationships

| Relationship | From → To | Meaning |
|---|---|---|
| `ENACTED_BY` | Instrument → Jurisdiction | Authority that issued it |
| `PART_OF` | Article → Instrument | Composition |
| `HAS_CHUNK` | Article → Chunk | Retrieval decomposition (ordered by `ordinal`) |
| `REFERENCES` | Article → Article | Parsed cross-reference ("see section 12(3)"). Loaded from clerk-curated manifest entries first (`cross_references`); LLM enrichment supplements where extraction is confident |
| `AMENDS` | Amendment → Instrument | Target instrument |
| `AMENDED_BY` | Instrument → Amendment | Inverse convenience, written explicitly |
| `SUPERSEDES` | Instrument → Instrument | Whole-instrument replacement |
| `REPEALS` | Instrument → Instrument | Explicit repeal edge (dates live on target) |
| `ABOUT` | Article → Concept | Topical linkage |
| `DEFINES` | Article → Concept | The article establishes or materially defines the concept |

## 4. Example subgraph

```mermaid
flowchart LR
    J((Jurisdiction<br/>rivermont)) <-- ENACTED_BY --- I1[Instrument<br/>By-law 2024-112<br/>Noise Control]
    I1 <-- PART_OF --- A1[Article 3<br/>Residential noise limits]
    I1 <-- PART_OF --- A2[Article 7<br/>Exemptions]
    A1 -- REFERENCES --> A2
    A1 -- ABOUT --> C1((Concept<br/>noise))
    I1 -- AMENDED_BY --> AM[Amendment<br/>2025-031<br/>published]
    AM -- AMENDS --> I1
    A1 <-- HAS_CHUNK --- K1[Chunk c0] & K2[Chunk c1]
```

## 5. Constraints and indexes (bootstrap DDL)

Applied idempotently at API startup and shipped in `deploy/neo4j/init/`.

```cypher
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

CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON c.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};
```

Note: the vector dimension is baked into the index definition. Changing the
embedding model means dropping and rebuilding the index plus re-embedding the
corpus; `ingest --rebuild-vectors` handles it. This is deliberate friction —
silent embedding-model drift would corrupt similarity semantics.

## 6. Current-law predicate

Nearly every read path filters through:

```cypher
(i.status = 'in_force')
AND (i.effective_from IS NULL OR i.effective_from <= date())
AND (i.effective_to IS NULL OR i.effective_to > date())
```

Historical questions opt out explicitly (`as_of` parameter on search/chat),
which relaxes the predicate to `date() >= effective_from` at the given date.
This makes time-travel a first-class query parameter rather than a prompt hack.

## 7. Versioning rules

1. Text edits inside an article produce new chunk IDs (hash includes text);
   the old chunks are deleted only after the replacement commits, inside the
   same transaction, keeping reads consistent.
2. An amended instrument keeps its ID. The amendment node records what changed.
3. A replaced instrument flips to `superseded`/`repealed` with `effective_to`
   set; it remains queryable for historical questions.
4. Nothing is ever hard-deleted except superseded chunk rows from a text edit.
   Corrections happen forward.

## 8. Known modeling gaps (accepted for phase 1)

- Schedules and forms are treated as articles with non-numeric `number`s;
  tables inside them lose structure (flattened text). Acceptable for Q&A;
  blocks any future "which form applies" feature until addressed.
- Definitions are linked to concepts only when `DEFINES` extraction is
  confident; the fallback is plain `ABOUT`. Definition-aware answering
  ("does 'dwelling unit' include a basement suite here?") currently relies on
  retrieval finding the defining section, not on ontology reasoning.
- Multilingual jurisdictions publishing parallel texts get parallel graphs
  joined by `(:Instrument)-[:TRANSLATION_OF]->(:Instrument)`, planned but not
  exercised in phase 1; questions in either language retrieve from the union.
