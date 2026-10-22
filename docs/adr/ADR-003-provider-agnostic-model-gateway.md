# ADR-003 · Provider-agnostic model gateway

Status: Accepted · 2026-08-02

## Context

Municipal policy on external LLM processing varies by jurisdiction and can
change mid-project (procurement, residency rulings, DPA negotiations).
Generation quality requirements are real but modest — short grounded answers —
so several model classes can satisfy them; which one is *permitted* is the
variable.

## Decision

All generation goes through an internal gateway module with an
OpenAI-compatible wire interface. Supported providers: Azure OpenAI, plain
OpenAI-compatible endpoints (vLLM, Ollama, LiteLLM proxies), and Anthropic
native. Provider selection is environment configuration only; no code or prompt
changes when switching.

## Rationale

1. Data-residency policy becomes a deploy-time decision, not an architecture
   decision. A municipality that starts on hosted models can move fully
   self-hosted without touching retrieval, prompts, or clients.
2. Cost control: the eval harness measures whether a cheaper model passes the
   gates; the gateway makes acting on that measurement trivial.
3. Vendor incidents become operational events (runbook RB-3), not outages of
   product capability.

## Alternatives considered

- **Standardize on one vendor SDK**: simplest code, unacceptable coupling given
  policy volatility documented in the product brief risks.
- **LangChain model abstraction**: rejected with the rest of the framework
  (see retrieval design §7); our gateway is ~150 lines including streaming
  parsers for two SSE dialects.

## Consequences

Positive: portability as above; a single place to enforce logging, timeouts,
token budgets, and future fallback routing.

Negative / accepted: we own SSE parsing quirks per provider (done, tested);
new-model-onset features (native tool calls, structured outputs) reach us late
or never — acceptable because our prompt contract is deliberately plain-text
with bracketed citations, not function-calling based.
