# ADR-004 · Article-boundary-aware chunking

Status: Accepted · 2026-07-20

## Context

Chunking strategy for legal text. Generic RAG practice — fixed-size windows
with overlap — treats the document as undifferentiated text. Municipal codes
are strongly structured: numbered sections, self-contained units of law, with
headings that carry meaning. Bad boundaries produce answers citing "section 3"
with text that is actually the tail of section 2.

## Decision

Parse instruments into articles first (per-jurisdiction heading profile:
regex list mapping this jurisdiction's numbering style), then chunk within
articles only: paragraph-boundary packing targeting ~320 tokens, sentence-safe
splitting on overflow, tail chunks ≥ 60 tokens or merged back. Chunks carry
`{article_id, ordinal}`; retrieval results always display instrument → article
→ heading regardless of which chunk matched.

## Rationale

1. Citations resolve to articles. If a chunk can straddle two sections, no
   citation produced from it is trustworthy — this would break ADR-005's
   contract at the root.
2. Legal sections are written to be read alone. Empirically (prototype
   measurements, 120 golden questions) boundary-respecting chunks improved
   hit@5 from 0.71 to 0.84 at equal token budget versus fixed windows.
3. Overlap between chunks is unnecessary when boundaries are semantic;
   dropping it cut indexed tokens ~18%.

## Alternatives considered

- **Fixed 512-token windows / overlap 64**: the default everywhere else; fails
  citation integrity as above.
- **One chunk per article**: cleanest citations, but some articles exceed
  embedding-model practical length and dilute similarity signal; splitting
  long ones retained precision in testing.
- **Hierarchical parent-document retrieval** (embed summaries, return parents):
  attractive later; requires a summarization pass we can't yet audit well.
  Noted as post-pilot candidate.

## Consequences

Positive: trustworthy citations; smaller index; heading text joins context
naturally.

Negative / accepted: ingestion depends on parsing quality per jurisdiction —
a wrong regex silently degrades everything downstream. Mitigation: ingest
report includes articles-per-instrument distribution compared against the
previous run; sudden shifts block publication (operations RB-2).
