# ADR-006 · Cross-lingual single index

Status: Accepted · 2026-08-02

## Context

The product must answer in the jurisdiction's official languages. Corpus source
text is typically monolingual (or parallel-text bilingual). Options: translate
queries into the corpus language before retrieval; translate the corpus into
each answer language; or retrieve cross-lingually from one multilingual index.

## Decision

Single multilingual embedding space (bge-m3) over source-language chunks.
Questions in any supported language embed directly against it; generation then
answers in the user's locale from retrieved source text. No query translation
step, no translated corpus copies.

## Rationale

1. One index means one freshness story. Translated corpora double/triple ingest
   complexity and create version-skew bugs ("French index lags English by four
   days") that are precisely the trust failures this product cannot afford.
2. bge-m3 was designed for cross-lingual retrieval; prototype checks on French
   and Spanish questions against English legal text showed usable recall, and
   the eval harness now measures each language properly rather than trusting
   vendor claims.
3. Legal terms of art should stay verbatim in citations even inside another
   language's answer; quoting the authoritative text with translation around
   it matches how clerks actually serve multilingual residents.

## Alternatives considered

- **Query translation** (translate question → corpus language): one more model
  call, one more failure point, and ambiguity compounds through translation.
- **Per-language corpora**: rejected for skew reasons above; revisited only if
  a jurisdiction mandates parallel-text publication anyway, in which case
  `TRANSLATION_OF` edges join them (already reserved in the ontology).

## Consequences

Positive: single pipeline, single freshness SLA, citations always point at the
authoritative-language source.

Negative / accepted: answer quality in non-source languages inherits both
retrieval quality and the generator's fluency; per-language thresholds will
need calibration (retrieval doc §9); embedding dimension (1024) is fixed per
ADR-001's rebuild caveat if the model ever changes.
