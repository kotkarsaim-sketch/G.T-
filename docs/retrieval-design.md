# CivicGraph Retrieval Design

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) |
| Related | [ADR-004](adr/ADR-004-article-boundary-chunking.md), [ADR-005](adr/ADR-005-grounded-generation-with-refusal.md), [ADR-006](adr/ADR-006-cross-lingual-single-index.md) |

---

## 1. Requirements

Legal retrieval differs from generic document search in four ways that shape
every decision below:

1. **Precision beats recall.** A wrong section cited confidently is worse than
   a referral. Thresholds and refusal exist because of this asymmetry.
2. **Structure is authoritative.** Section numbers, article boundaries, and
   instrument status are signal, not metadata. A query like "bylaw 2019-14
   section 6" must resolve exactly, not semantically.
3. **Currency is part of correctness.** Retrieval over repealed text without
   status filtering produces confident nonsense.
4. **Cross-references are queries.** "Can I do X" often resolves only by
   following the reference graph (the general prohibition plus the exemption
   in another article).

## 2. Indexing units

Articles are chunked with boundary awareness: a chunk never spans two
articles; long articles split at paragraph boundaries targeting ~320 tokens
with sentence-level packing; the tail chunk keeps ≥ 60 tokens or merges back.
Rationale and rejected alternatives in ADR-004.

Each chunk carries its article's identity into retrieval results, so every
score can be surfaced to the user as *Instrument number → Article number →
heading*.

## 3. Candidate generation (three channels, run in parallel)

### 3.1 Dense channel

Query embedded by bge-m3; top `k=40` via Neo4j's native vector index,
cosine similarity. Multilingual questions retrieve English text directly —
no translation step (ADR-006).

### 3.2 Lexical channel

Neo4j fulltext index over chunk text (BM25 ranking). This catches exact legal
vocabulary that embeddings blur: defined terms ("dwelling unit"), Latin tags,
instrument numbers mentioned in text.

### 3.3 Structural channel

Regex extraction of section/instrument references from the question
(`\b(\d{4}-\d{1,3})\b` for instrument numbers, `\bsection (\d+(?:\.\d+)*)\b`
for articles). Exact lookups bypass scoring entirely; structural hits always
enter the candidate pool regardless of rank. This channel is what makes
clerk-style queries work on day one.

## 4. Fusion

Reciprocal Rank Fusion with k=60:

```
RRF(chunk) = Σ_channels  1 / (60 + rank_channel(chunk))
```

Structural hits receive a fixed bonus of +0.5 so an exact section match wins
over a plausible semantic neighbor. RRF was chosen over weighted linear fusion
because it needs no score-scale calibration between BM25 and cosine — one
less thing to re-tune per embedding model. Deduplication is by chunk ID;
per-article caps (max 3 chunks) prevent one long article from occupying the
whole context window.

Early termination: if fewer than 8 fused candidates remain after dedup, the
expansion stage widens sibling limits rather than lowering thresholds.

## 5. Graph expansion

Seeds (top ~12 fused chunks) expand through the ontology:

```cypher
UNWIND $seed_ids AS sid
MATCH (a:Article)-[:HAS_CHUNK]->(c:Chunk {id: sid})
MATCH (a)-[:PART_OF]->(i:Instrument)
WHERE current_law_predicate(i)
WITH a, i, [(a)-[:HAS_CHUNK]->(s) | s][..2] AS siblings,
     [(a)-[:REFERENCES]->(r) | r][..3] AS refs
...
```

(Simplified; implementation in `server/src/civic/retrieval.py`.)

Expansion adds, in priority order: sibling chunks of a seed's article
(completing truncated context), directly referenced articles (exemptions,
definitions), parent instrument metadata (title, effective dates for the
citation block). One hop only — two hops measurably diluted precision during
prototyping while adding latency. Expansion candidates enter the context pool
tagged as `expanded`, never as primary citations unless the generator actually
cites them.

Status filtering happens here, not post-hoc: repealed instruments cannot leak
into context at all when answering about current law.

## 6. Grounded generation and refusal (ADR-005)

Context assembly: up to 8 passages, each rendered as

```
[3] By-law 2024-112, s. 3.1 — Noise limits in residential zones
    <chunk text>
```

System prompt contract (abridged; full text in `prompts.py`):

- Answer only from the numbered sources; cite every factual claim as `[n]`.
- If sources conflict or are insufficient, say so and stop.
- Match the user's language; quote legal thresholds verbatim with citation.
- Advisory framings get redirected to the clerk's office; never opine on
  legality for a specific person's situation.

**Refusal rule**: refuse before generation when the best dense cosine similarity
across candidates is below `RETRIEVAL_MIN_SCORE` (default 0.35) and no
structural (exact section/instrument number) hit exists — an exact lookup is
authoritative regardless of similarity. Refusal copy is
fixed text reviewed by counsel — not model-generated — plus the clerk contact
and suggested reformulation. Post-generation, `[n]` markers outside the
provided source range are stripped (`citations.py`); if every marker in an
answer is stripped, the answer is replaced by the refusal path. That last
check is the single most important line of code in the system.

## 7. Why no orchestration framework

LangChain/LlamaIndex were prototyped and dropped. The valuable logic here is
roughly 600 lines of explicit code — three retrievers, fusion, expansion, two
prompts, a citation validator — where we need deterministic behavior, stable
IDs, and Cypher we can profile. Framework abstractions changed API surface
three times during the prototype month; our pipeline hasn't changed shape.
The tradeoff is honest: we own streaming plumbing and provider quirks in
`llm.py`. For this size of system, owning it is cheaper than tracking it.

## 8. Evaluation hooks

Every retrieval stage emits structured logs (`query_id`, stage, candidate ids,
scores), which is what makes offline regression testing possible: replay a
golden query set against a candidate config change and diff hit@5/MRR/citation
precision before shipping. Methodology and gates: [evaluation.md](evaluation.md).

Tuning defaults live in settings, per-environment:

| Parameter | Default | Notes |
|---|---|---|
| `RETRIEVAL_VECTOR_K` | 40 | Generous pre-fusion; cheap at this corpus size |
| `RETRIEVAL_FULLTEXT_K` | 40 | Same rationale |
| `RETRIEVAL_FINAL_K` | 8 | Context passages after expansion |
| `RETRIEVAL_MIN_SCORE` | 0.35 | Refusal threshold on normalized fused score |
| `ENABLE_RERANK` | false | Enable once eval shows net gain over expansion |

## 9. Planned improvements (post-pilot)

- Query rewriting for multi-part questions (split-and-fan-out), gated on eval.
- Definition-aware retrieval: boost `DEFINES` edges for questions containing
  quoted terms.
- Per-language threshold calibration: refusal rates differ across languages;
  one global threshold will be replaced by per-language values from eval data.
