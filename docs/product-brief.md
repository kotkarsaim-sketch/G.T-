# CivicGraph Product Brief

**Civic Knowledge Graphs: Democratizing Local Legal Intelligence**

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) |
| Owner | Municipal Platforms Team |
| Reviewers | City Clerk's Office; Legal; IT Architecture Board |
| Alignment | UN SDG 16 (16.3, 16.6, 16.10), SDG 11 (11.3) |

---

## 1. Problem

Municipal law is where citizens actually meet the law — zoning, noise, animal
control, business licensing, parking, waste. It is also the level of law with
the least legal support infrastructure. Three failure modes recur in every
jurisdiction we studied:

1. **Opacity.** A resident who wants to know whether a home bakery is
   permitted must navigate a code organized by legal instrument, not by
   question. The relevant rules are often scattered across a zoning by-law,
   a business licensing by-law, and a council resolution.
2. **Front-counter load.** Clerk and 311 staff answer the same several hundred
   questions repeatedly. In comparable deployments, routine interpretive
   questions consume 20–40% of front-counter capacity.
3. **Version confusion.** Codes are amended frequently. Residents find
   outdated PDFs through search engines and act on repealed text. Staff spend
   time correcting them.

The cost is not only inefficiency. When people cannot understand the rules,
compliance becomes accidental, trust in local institutions erodes, and
participation in hearings skews toward those who can afford professional advice.

## 2. Product thesis

If the municipal code is modeled as a **knowledge graph** — instruments,
articles, amendments, cross-references, concepts — and queried through a
retrieval-augmented language model that is **only allowed to cite that graph**,
then residents get accurate answers in plain language, and staff get a defensible
tool because every sentence traces to an article in force.

The graph matters more than the model. Language models change yearly; a clean,
versioned representation of the code outlives them and remains useful for open
data, hearing prep, and inter-departmental tooling regardless of the chat layer.

## 3. Users and jobs to be done

| Persona | Job | Current path | CivicGraph path |
|---|---|---|---|
| Resident (no legal training) | "Can I keep bees in my backyard?" | Search PDFs → call 311 → site visit | Ask in plain language; get cited answer in their language |
| Front-counter clerk | Answer interpretive question quickly, with confidence it is current | Binders + intranet + memory | Same interface, but with section-level citations they can verify |
| Policy analyst / counsel | Impact scan: which instruments touch short-term rentals? | Manual full-text reading across instruments | Structured queries over concepts and cross-references |
| Council / communications | Reduce repeat inquiries without reducing transparency | FAQ pages that go stale | Deflection with audit trail; every answer shows its sources |

Explicitly **not** a user group: lawyers seeking formal opinions. The product
provides legal *information*, never legal *advice*; see §7.

## 4. Scope

### Phase 1 (this repository)

- Single jurisdiction; municipal instruments only: by-laws, ordinances,
  resolutions, council-approved policies.
- Question answering over the code with mandatory citations to article level.
- Temporal correctness: answers reflect law in force today; historical questions
  ("what did the noise by-law say before 2024?") resolve against amendment records.
- Multilingual question answering (initial targets: English plus one or two
  jurisdiction-mandated languages; architecture is language-agnostic).
- Hybrid retrieval: dense + keyword + exact section lookup, expanded through the
  reference graph.
- Admin ingestion pipeline with human review gate for amendments.

### Phase 2 candidates (out of scope now)

- Provincial/state statutes and case-law integration.
- Proactive compliance checkers ("describe my project, get a requirements list").
- Hearing-calendar awareness and draft-amendment tracking beyond a review queue.
- Formal opinion drafting support for counsel.

### Non-goals

- Legal advice, representation, or forms filing.
- Enforcement decisions of any kind.
- General web QA: the system refuses questions outside the corpus rather than
  answering from model memory. This is a product feature, not a limitation.

## 5. Success metrics

Pilot targets, measured over six months at one mid-size municipality:

| Metric | Target | Source |
|---|---|---|
| Answer-with-citation task success (user found what they needed) | ≥ 85% | In-product feedback + quarterly panel study |
| Citation precision (cited article supports the claim) | ≥ 95% | Weekly human audit, 50-sample |
| Harmful fabrication rate (answer states rule with no corpus basis) | < 0.5%, target 0 | Audit + eval harness gate |
| Repeat-inquiry deflection at clerk/311 tier-1 | ≥ 25% | 311 ticket categorization |
| Median time-to-answer vs. phone baseline | ≤ 2 min vs. ~2 days | Product telemetry |
| p95 first token / complete answer latency | ≤ 1.5 s / ≤ 8 s | Server telemetry |

Evaluation methodology: [docs/evaluation.md](evaluation.md).

## 6. Constraints and assumptions

- Corpus size for a mid-size city: roughly 40–120 instruments, 2,500–8,000
  articles, under 50 MB of text. Trivial for Neo4j; retrieval quality is the
  engineering problem, not scale.
- Source documents arrive as HTML or PDF from the clerk's office, with a
  structured manifest. OCR for scanned legacy documents is accepted as
  upstream debt and flagged per document.
- Deployment must be able to run entirely inside municipal infrastructure
  (data residency). Hosted LLM APIs are permitted where policy allows; the
  gateway abstraction keeps self-hosted fallback viable (ADR-003).
- Languages: embedding and generation stacks must handle at minimum the
  jurisdiction's official languages. Cross-lingual retrieval via a single
  multilingual index (ADR-006).

## 7. Trust boundaries

Three hard rules govern everything else:

1. **No uncited claims.** Generation prompts require bracketed citations;
   post-processing strips any citation that does not map to a retrieved source,
   and answers whose citations were all stripped are converted to referrals.
2. **Refuse rather than guess.** Below the evidence threshold, the system says
   so and routes the user to the clerk's office contact. Refusal rate is
   monitored; a rising refusal rate on previously-answerable categories is a
   corpus-quality alarm, not a model-tuning knob.
3. **Information, not advice.** Every session carries a persistent disclaimer;
   prompts instruct the model to decline advisory framings ("should I sue",
   "is this legal for me specifically") and redirect to counsel or the clerk.

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stale corpus after an amendment cycle | Medium | High (wrong law presented as current) | Effective-date modeling in the ontology; nightly freshness job compares source-of-truth feed; ingest SLA of 2 business days |
| Prompt injection via crafted document text | Low | Medium | Retrieved text is data, never instructions; hardened system prompt; injection probes in eval set (security doc §4) |
| Over-trust: users treat answers as binding | Medium | High | Persistent disclaimer, citation-first UI, refusal copy reviewed by counsel |
| Multilingual answer quality below bar | Medium | Medium | Golden set includes translated questions; per-language metrics gate releases (evaluation doc §3) |
| LLM vendor/policy shift | High | Low | Provider-agnostic gateway; embeddings served locally; graph survives any model swap |
| Ingestion errors corrupt the graph | Low | High | Idempotent MERGE writes, content hashing, dry-run mode, review queue for amendments before publication |

## 9. Open questions

1. Does the adopting municipality mandate specific hosting (on-prem vs.
   municipal cloud region)? Affects LLM provider default only.
2. Which additional languages beyond English are required for launch?
3. Who owns the amendment review queue operationally — clerk's office or IT?
4. Retention period for query logs: proposed 90 days raw, aggregated thereafter
   (see security doc §5); requires privacy officer sign-off.
