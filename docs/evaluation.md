# CivicGraph Evaluation

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) |

Evaluation is the release gate. Nothing ships — code, prompts, embedding
models, retrieval parameters — without passing the harness against the frozen
golden set plus any regression cases accumulated since the last release.

## 1. Golden set

- **300 question/answer pairs** authored by clerk's office staff and one
  reviewing lawyer, spanning 12 categories (zoning, noise, animals, business
  licensing, parking, waste, building, parks, procedures, definitions,
  cross-instrument questions, historical questions).
- **60 multilingual items** (per launch language), translated from English
  originals with independent back-translation review.
- **30 adversarial items**: injection attempts embedded in plausible questions,
  out-of-scope questions that *look* in-scope ("what does provincial law say
  about X"), and questions about repealed text where correct behavior is
  refusal-with-current-answer.
- Each item stores: expected article citations (required ≥ 1 match),
  forbidden citations (repealed sections), expected behavior (`answer` |
  `refuse` | `redirect`).

The set is data, versioned with the corpus snapshot hash; a golden item is
retired only by recorded decision, never silently.

## 2. Offline metrics

| Metric | Definition | Gate |
|---|---|---|
| Retrieval hit@5 | Expected article in top-5 fused results | ≥ 0.85 |
| MRR over expected articles | Standard | Report, no gate yet |
| Citation precision | Sampled answers: cited article supports claim | ≥ 0.95 |
| Faithfulness | Judge model + 10% human audit: claims entailed by cited text | ≥ 0.90 |
| Refusal correctness | Correct behavior on refuse/redirect/adversarial subsets | ≥ 0.98 on adversarial |
| Fabrication count | Answers stating rules absent from corpus | 0 tolerance |
| Latency p95 | First token / complete, staging hardware | ≤ 1.5 s / ≤ 8 s |

Judge-model scores are always backed by human audit of a fixed sample; judge
agreement with humans is itself tracked so drift in the judge gets caught.

## 3. Multilingual protocol

Per-language gates mirror the main gates at slightly relaxed retrieval
thresholds during pilot (hit@5 ≥ 0.80). Languages failing two consecutive
releases get a documented remediation plan — typically corpus translation
quality or per-language threshold calibration — not silent threshold decay.

## 4. What runs when

| Trigger | Harness scope |
|---|---|
| PR touching `server/src` | Retrieval-only subset (~5 min): hit@5/MRR on cached embeddings |
| PR touching prompts or LLM config | Full generation eval (staging quota) |
| Nightly | Full suite vs. latest corpus ingest |
| Corpus update published | Diff-triggered: all golden items citing changed articles re-run |
| Pre-release | Full suite + latency on staging + manual audit sample |

The runnable smoke harness (`server/dev/eval_harness.py` + `evals/golden.yaml`,
24 cases over the bundled corpus, `make eval`) implements the same gate
structure: retrieval hit@5 and refusal correctness are hard gates; citation
on-target rate is reported per run.

Baseline on the local pilot stack (2026-08-26): with English-only dev
embeddings (bge-small-en), hit@5 1.00 / refusal 1.00 / citation on-target 0.53,
and the French case failed retrieval as expected. After switching the dev shim
to `paraphrase-multilingual-MiniLM-L12-v2` and running
`ingest --re-embed`, prod-profile gates pass: hit@5 **0.90** (including
`fr-bees` — the ADR-006 cross-lingual claim holds), refusal correctness
**1.00** (4/4), citation on-target **0.60**. Two findings worth keeping in
view: adversarial-phrasing retrieval (`injection-credentials`) and
borderline-rank cases sit near the top-5 cutoff and vary by embedding model;
and refusal behavior on adjacent-scope questions (`refuse-parking`) is
**stochastic with a 1.5B generator** — it refused in most runs and answered
with adjacent cited provisions in one. Both are generator/model-tier issues,
addressed by the gateway upgrade path, not retrieval defects. Run the prod
profile (`--profile prod`) when multilingual must be gated.

## 5. Online signals (pilot instrumentation)

- Per-answer thumbs with optional free-text → triaged weekly (RB-4).
- Citation click-through rate: users opening the canonical source. A falling
  rate alongside stable satisfaction suggests citation presentation problems;
  a rising rate is the transparency metric working.
- Escalation share: sessions ending in "contact the clerk" clicks, tracked as
  the honest deflection denominator.
- Quarterly panel study (product brief §5) remains the ground truth for
  task-success claims; telemetry only localizes problems.

## 6. Known limits of this program

Golden sets encode today's corpus and today's question distribution; they go
stale like everything else. Mitigations: quarterly refresh from live query
clusters (privacy-preserving category sampling), adversarial subset owned by a
different reviewer than the functional set, and the refusal-rate alarm as an
unbiased production signal that something drifted before the golden set notices.
