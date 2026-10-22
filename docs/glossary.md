# Glossary

**Article / section** — The numbered unit of a legal instrument ("section 12"
or "article 12" depending on jurisdiction drafting convention). CivicGraph
models both as `Article`; display follows the source document's own term.

**By-law / ordinance** — A law enacted by a municipal council under powers
delegated by higher-level statute. Treated as synonyms at the schema level
(`kind` field preserves the jurisdiction's term).

**Chunk** — The unit actually embedded and retrieved: a paragraph-aligned slice
of one article, never spanning articles.

**Concept** — A curated topical label ('short-term rental') linking articles
across instruments; the light-weight ontology layer above raw text.

**Cross-reference** — An explicit pointer inside legal text to another section
("as provided in section 7"). Parsed into `REFERENCES` edges; often where the
real answer lives (exemptions, definitions).

**Effective date / in force** — The date a provision becomes legally operative.
"In force" is the temporal filter applied to nearly every retrieval query;
text published but not yet effective is excluded from current-law answers.

**Enabling statute** — The higher-level law authorizing a municipality to enact
a given by-law. Out of corpus scope in phase 1; referenced in metadata when the
clerk provides it.

**Grounding** — Constraining generated text to retrieved sources. In CivicGraph:
numbered context passages, mandatory `[n]` citations, post-generation marker
validation, refusal below evidence threshold.

**Hybrid retrieval** — Combining dense vector similarity, lexical (BM25)
scoring, and structural lookups; fusion via reciprocal rank fusion.

**Instrument** — Any published legal document: by-law, ordinance, resolution,
council policy.

**Preamble** — Unnumbered introductory text of an instrument (enacting clause,
effective statement). Modeled as an `Article` with number "Preamble".

**RAG** — Retrieval-augmented generation: retrieve relevant passages, then have
the model compose an answer constrained to them.

**Reciprocal Rank Fusion (RRF)** — Score = Σ 1/(k + rank) across ranked lists;
k=60 standard. Chosen because it needs no cross-scorer calibration.

**Repeal / supersede** — Ending an instrument's force (repeal) or replacing it
with a successor (supersede). Both keep the historical record queryable via
`effective_to`.

**Schedule** — Tabular or form-like appendix to an instrument. Flattened to
text in phase 1 (known limitation).

**SSE (Server-Sent Events)** — HTTP streaming protocol used for chat responses;
chosen over WebSockets for proxy-friendliness and automatic reconnection.

**TEI** — Hugging Face Text Embeddings Inference: the container serving bge-m3
embeddings and (optionally) the reranker.
