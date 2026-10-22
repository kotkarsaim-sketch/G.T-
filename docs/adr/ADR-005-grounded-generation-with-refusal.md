# ADR-005 · Grounded generation with hard refusal

Status: Accepted · 2026-08-02

## Context

A language model answering questions about law will occasionally produce
plausible, confident, false statements. For this product the asymmetry is
extreme: a fabricated rule that a resident relies on is institutional harm,
while a refusal costs seconds of user time. We need an enforceable mechanism,
not prompt guidance alone.

## Decision

Four interlocking controls:

1. **Evidence gate before generation.** If no candidate clears
   `RETRIEVAL_MIN_SCORE`, emit fixed refusal copy (counsel-approved) plus clerk
   contact. The model never sees the question unanswered.
2. **Citation-mandatory prompting.** Context is rendered as numbered passages;
   system prompt requires `[n]` markers per factual claim.
3. **Post-generation validation.** Markers referencing sources not provided are
   stripped mechanically (`citations.py`). If all markers are stripped, the
   answer is replaced by the refusal path. This catches the failure mode where
   the model cites confidently from memory.
4. **Refusal over hedging.** When evidence exists but conflicts or covers only
   part of the question, the model states exactly what the corpus supports and
   names the gap, rather than extrapolating.

## Rationale

Prompt-only grounding fails silently and unmeasurably. Controls 1, 3, and 4
are mechanical checks whose pass rate appears in eval gates (evaluation doc §2)
and production telemetry (refusal-rate alarm). Making refusal *observable* is
what turns "the model seems accurate" into an auditable claim.

## Alternatives considered

- **Trust + spot audit**: rejected; audit finds failures after users absorb them.
- **Function-calling forced citations**: couples us to provider-specific
  structured-output behavior (see ADR-003 consequences); plain markers validate
  identically across providers.
- **NLI-based claim verification post-hoc**: adds latency and its own error
  rates at pilot scale; revisit if citation precision drifts below gate.

## Consequences

Positive: fabrication has a mechanical tripwire; refusals are countable and
their copy legally pre-approved; works unchanged across model swaps.

Negative / accepted: occasional over-refusal on legitimately answerable but
awkwardly-phrased questions — mitigated by suggested-reformulation copy and
monitored via the daily refusal-rate metric; threshold tuning is an eval-driven
process, never adjusted ad hoc in production.
