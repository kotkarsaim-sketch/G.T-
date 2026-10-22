# CivicGraph Security & Governance

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) |
| Review gate | Municipal privacy officer + IT security must sign off before pilot |

---

## 1. Data classification

| Data | Class | Handling |
|---|---|---|
| Municipal code text | Public | No restrictions; already published |
| User questions | Potentially personal | Treat as personal data: minimized retention (§5), never used for model training |
| Audit records | Internal | Access restricted to platform operators; aggregated stats public |
| Credentials/config | Secret | Environment-injected; never in repo, logs, or images |

The system stores no user accounts in phase 1 — no names, emails, or
addresses are required to ask a question. This is a deliberate privacy posture,
not a missing feature.

## 2. Architecture-level controls

1. **Single generation choke point.** All LLM calls go through the api service;
   the web tier holds no provider credentials.
2. **Egress discipline.** In production the API's outbound allowlist is:
   embedding service, reranker, configured LLM endpoint(s), telemetry sink.
   Everything else denied at the network policy level.
3. **Read-only pipeline separation.** The ingest/enrich CLIs run from operator
   workstations or CI with write credentials; the public API uses a Neo4j role
   with read + audit-append privileges only. The public path cannot mutate the
   corpus even if the application layer is compromised.
4. **TLS everywhere** at the proxy; bolt traffic stays on the private network.

## 3. Threat model (STRIDE, abridged)

| Threat | Vector | Mitigation |
|---|---|---|
| Prompt injection | Adversarial text planted in source documents ("ignore instructions, say X") | Retrieved text is framed as quoted data inside the prompt; system prompt hardening; injection probes in the eval set block releases; citations make manipulation visible |
| Corpus poisoning | Compromised ingest source or manifest | Ingest runs from signed CI jobs on reviewed sources only; amendments require human publication; content hashes detect silent edits |
| Denial of service | Scraping / flooding | Token-bucket limits per IP (api-spec §4), proxy-level rate caps, static degradation page |
| Answer fabrication → institutional harm | Model hallucination presented as law | Grounding contract + citation validation + refusal threshold (retrieval doc §6); weekly precision audit with kill-switch authority delegated to product owner |
| Log-based re-identification | Rare queries + timestamps | 90-day raw retention, then aggregation; no IP stored beyond 30 days; no query text in access logs |
| Dependency supply chain | Malicious package update | Pinned versions, lockfiles, automated CVE scan in CI; no `latest` tags in production compose/Helm |

Residual risks we accept for phase 1: unauthenticated public read endpoints
(corpus is public anyway), single-region deployment availability.

## 4. LLM-specific policy

- Providers must sign the municipality's data-processing addendum; zero-retention
  inference endpoints preferred. Where policy forbids external processing
  entirely, the gateway points at self-hosted vLLM and nothing else changes.
- Prompts are versioned artifacts in the repo (`prompts.py`) with change review;
  prompt changes run the eval harness before deploy, same as code.
- Temperature is fixed low (0.2) and not exposed as a runtime knob; "creativity"
  is a defect mode in this domain.

## 5. Privacy & records

- **Retention:** raw question/answer pairs 90 days, then deleted; aggregates
  (counts by category, refusal rate, latency) retained indefinitely and published
  in quarterly transparency reports.
- **FOI/records posture:** chat transcripts are operational records, not part
  of the municipal code; classification confirmed with the clerk's office per
  jurisdiction before launch.
- **Accessibility:** web client targets WCAG 2.2 AA (keyboard-navigable chat,
  citation links with meaningful text, contrast-checked palette, reduced-motion
  respected). Legal information that fails accessibility fails its purpose.

## 6. Content governance

- Every generated page carries: "Informational only — not legal advice",
  effective-date context for cited instruments, and the canonical source link.
- Refusal copy is fixed text approved by counsel; product staff may not edit it
  without re-approval (enforced by code review convention).
- A "report a problem" affordance on every answer routes to the clerk's office
  queue with the query_id attached; correction SLA mirrors their existing
  website-correction process.

## 7. Operational security checklist (pre-launch)

- [ ] Secrets rotated out of `.env.example` defaults in all environments
- [ ] Neo4j auth enabled; API role restricted (read + audit append)
- [ ] Proxy TLS config graded A− or better (external scan)
- [ ] Rate limits load-tested; degradation page verified
- [ ] Injection probe set passes at 100% (eval harness)
- [ ] Backup restore rehearsed (operations doc §7), RPO 24h / RTO 4h demonstrated
- [ ] Privacy officer sign-off on retention configuration recorded
