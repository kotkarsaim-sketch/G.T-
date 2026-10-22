# ADR-002 · FastAPI service layer

Status: Accepted · 2026-07-14

## Context

The api service must stream SSE responses, call async inference services, talk
to Neo4j concurrently, and expose typed REST contracts. Candidate stacks:
Python (FastAPI), Node/TypeScript (NestJS/Next API routes), Go.

## Decision

FastAPI on Python 3.12, Pydantic v2 settings/models, Uvicorn workers behind a
reverse proxy.

## Rationale

1. The pipeline half of this system (embedding batching, extraction prompts,
   token accounting) is Python-native regardless of the web framework choice;
   splitting languages across api and pipeline would double deployment surface
   for zero benefit here.
2. First-class SSE via `StreamingResponse`; async httpx for provider calls.
3. Pydantic models double as the OpenAPI contract consumed by the web client
   and external integrators.
4. Team reality: municipal platform maintainers will find Python data code more
   approachable than a bespoke Node ML layer.

## Alternatives considered

- **NestJS**: better long-lived-connection ergonometrics in theory; but every
  NLP utility ends up calling a Python sidecar anyway.
- **Go**: best raw throughput; irrelevant at 5 rps design load, worst ergonomics
  for prompt/extraction iteration.
- **Serverless functions**: cold-start latency on streaming chat and vendor
  lock on SSE semantics made this a quick rejection.

## Consequences

Positive: one language across api + pipelines; typed contracts exported from
the same code that enforces them; hiring pool familiar.

Negative / accepted: GIL constrains CPU-bound work — irrelevant today since
heavy lifting happens in Neo4j and TEI; if it ever matters, reranking moves to
its own service before the API gets complicated.
