# CivicGraph Operations

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) |
| Audience | Platform operators; assumes Docker/Kubernetes familiarity |

---

## 1. Environments

| Env | Purpose | Data | LLM backend |
|---|---|---|---|
| `dev` | Local docker-compose | Fictional sample corpus | Ollama or any local OpenAI-compatible server |
| `staging` | Release rehearsal, eval runs against real corpus snapshot | Anonymized production snapshot | Same class as prod, lower quota |
| `prod` | Public pilot | Live corpus | Per municipal policy: Azure OpenAI region-hosted or self-hosted vLLM |

Config is environment-only (12-factor); no per-env image builds.

## 2. Deployment topology

Phase 1 pilot: single VM (4 vCPU / 16 GB) running compose — honest sizing for
5 rps design load, keeps the ops story learnable. Kubernetes migration is
prepared but not required:

- API is stateless → Deployment + HPA on CPU/RPS.
- Neo4j → StatefulSet; causal clustering (Enterprise) when HA becomes a
  requirement; Community edition single-instance until then, accepted risk.
- TEI → Deployment sized to one replica (model fits comfortably in RAM).

Release process: CI builds images on tag → staging deploy → eval harness gate
(evaluation doc §5) → promote identical digests to prod → smoke check
(`/readyz`, one scripted golden question). Rollback = redeploy previous digest;
graph schema changes are backward-compatible by policy (additive only within
a release train).

## 3. SLOs

| SLI | SLO |
|---|---|
| Availability (chat + search succeed or degrade gracefully) | 99.5% monthly |
| First token latency p95 | ≤ 1.5 s |
| Complete answer p95 | ≤ 8 s |
| Refusal correctness (refusals that should have been answers) | ≥ 98% via audit |
| Citation precision | ≥ 95% via audit |

Error budget policy: two consecutive weeks over budget freezes feature deploys
in favor of reliability work.

## 4. Monitoring

Metrics (Prometheus): request rates by route/status, SSE stream durations,
stage latencies (embed/retrieve/expand/generate), refusal rate, token usage,
Neo4j heap/page-cache hits, TEI batch queue depth.

LLM tracing: every generation logs prompt template version, model id, source
chunk ids, token counts to the structured log; a Langfuse instance is optional
but recommended during tuning phases.

Alerts worth paging on (everything else goes to the daily digest):

- Chat error-rate (non-refusal 5xx) > 2% for 10 min
- p95 first token > 3 s for 15 min
- Refusal rate > 40% daily (corpus or retrieval regression alarm)
- Freshness job failure (§6)

## 5. Capacity and cost envelope

Assumptions: mid-size city (~300k residents), 10k chat sessions/month at pilot
steady state, ~600 tokens generated per session, ~3k tokens of context each.

| Item | Estimate | Basis |
|---|---|---|
| Embeddings (self-hosted CPU) | ~$0 marginal | bge-m3 on existing VM |
| Generation, hosted mini-class model | ~$25–60/month | At ~6M tokens/month, order-of-magnitude only |
| Generation, frontier-class model | ~$250–500/month | Only if eval shows quality delta justifying it — measure first |
| Self-hosted GPU option (24 GB VRAM) | One GPU box | ~14B-class model serves 5 rps with headroom |
| Neo4j storage | < 5 GB for years | Full mid-size corpus ≈ tens of MB text + vectors |

The cost curve is dominated by generation choices, which is why the gateway
exists: switch models per-environment without touching retrieval code, and let
the eval harness decide what quality actually requires.

## 6. Runbooks

### RB-1 · Corpus freshness drift

Nightly job compares official feed hash vs. `Instrument.content_hash`.
On mismatch: opens ticket, sets affected instruments' `status` metadata flag
`stale_source`. Operator: run ingest for changed instruments → review diff
summary → publish. SLA: 2 business days from official publication.

### RB-2 · Refusal rate spike (>40% daily)

Almost always ingestion or index trouble, not model behavior. Check in order:
(1) vector index population count vs. chunk count, (2) last ingest job report,
(3) embedding service health (`/readyz` covers it), (4) whether a jurisdiction
profile regex change broke article parsing (compare articles-per-instrument
against yesterday).

### RB-3 · LLM provider outage

Gateway marks provider unhealthy after 3 consecutive failures; if a fallback
provider is configured it takes over automatically; otherwise chat degrades to
sources-only streaming (`finish: degraded`). Users see an explanation notice;
no action required, but file the vendor incident.

### RB-4 · Bad answer reported (query_id supplied)

Pull audit record → reproduce via `/v1/search` with same query → classify:
stale corpus (RB-1) / retrieval miss (add to eval set, tune) / generation error
(prompt issue, eval set) / user misunderstanding (no action). Weekly triage
feeds the eval golden set — complaints become tests.

## 7. Backup and DR

- Neo4j: daily full backup + transaction logs; retain 14 dailies, 8 weeklies.
- Restore drill quarterly; targets RPO ≤ 24 h, RTO ≤ 4 h (single-VM reality).
- The corpus itself lives in git-versioned source exports; the graph is
  rebuildable from scratch via `ingest --full` in under 20 minutes at demo
  scale — treat the graph as derived state and the repo as truth where possible.

## 8. Access management

Operators authenticate to hosts via municipal SSO/SSH policy; no shared
credentials. Neo4j accounts: `civic_api` (read+append), `civic_pipeline`
(write), `admin` (break-glass, credential rotation every 90 days). Admin CLI
actions are logged to the audit stream like any other mutation.
