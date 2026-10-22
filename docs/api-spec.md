# CivicGraph API Specification

| | |
|---|---|
| Document status | Draft for review |
| Version | 0.3 (2026-08-26) · matches `civic.main` OpenAPI export |
| Base URL | `/v1` under the api service (default `http://localhost:8000`) |

---

## 1. Conventions

- JSON bodies, UTF-8. Dates ISO-8601. Errors follow RFC 7807 (`application/problem+json`)
  with a stable `code` field for programmatic handling.
- Streaming endpoints use Server-Sent Events.
- Public read endpoints require no auth in phase 1. Admin routes (documented
  separately, not implemented yet) will require OIDC JWTs with an `admin` claim.
- All responses carry `X-Request-ID`; supply your own via header to correlate.

## 2. Endpoints

### 2.1 `POST /v1/chat` — grounded Q&A (SSE stream)

Request:

```json
{
  "question": "Can I keep bees in my backyard on Elm Street?",
  "jurisdiction": "rivermont",
  "locale": "en",
  "as_of": null,
  "history": []
}
```

| Field | Type | Notes |
|---|---|---|
| `question` | string, 3–2000 chars | Required |
| `jurisdiction` | string | Optional in phase 1 (single jurisdiction); validated if provided |
| `locale` | BCP-47 | Answer language; defaults to server locale policy |
| `as_of` | date | Historical mode; default = current law |
| `history` | array ≤ 6 of `{role, content}` | Client-managed conversational context |

Response: `text/event-stream`, events in order:

```
event: meta
data: {"query_id":"q_01J...","sources":[{"n":1,"instrument":{"id":"rivermont-bylaw-2024-112","number":"2024-112","title":"Noise Control By-law"},"article":{"id":"...#s-7","number":"7","heading":"Exemptions"},"url":"https://...","score":0.61,"origin":"seed"}]}

event: token
data: {"text":"Yes, under certain conditions. "}

event: token
data: {"text":"By-law 2024-112 s. 7 exempts registered hives [1]."}

event: citations
data: {"used":[1],"sources":[ ... same shape as meta.sources ... ]}

event: done
data: {"finish":"complete","latency_ms":3410}
```

Refusal path emits `event: notice` with fixed counsel-reviewed copy and
`done.finish = "refused"` instead of token events. Generation-unavailable
emits `notice` followed by the source list only (`finish = "degraded"`).

Client rules: render `meta.sources` immediately (citation panel fills before
text streams); treat unknown event types as no-ops for forward compatibility.

### 2.2 `POST /v1/search` — retrieval without generation

```json
{ "query": "noise exemption construction", "mode": "hybrid", "limit": 10 }
```

`mode`: `hybrid` (default) | `vector` | `keyword`. Returns ranked passages
with instrument/article metadata, scores, and `as_of` support identical to
chat. Used by the portal's non-chat browse view and by the eval harness.

### 2.3 `GET /v1/instruments`

Query params: `kind`, `status` (default `in_force`), `q` (title contains),
`limit` ≤ 100, `cursor`.

```json
{
  "items": [{
    "id": "rivermont-bylaw-2024-112",
    "kind": "bylaw",
    "number": "2024-112",
    "title": "Noise Control By-law",
    "status": "in_force",
    "effective_from": "2024-07-01",
    "source_url": "https://...",
    "language": "en"
  }],
  "next_cursor": null
}
```

### 2.4 `GET /v1/instruments/{id}` — full instrument with ordered articles

### 2.5 `GET /v1/articles/{id}` — article detail incl. outgoing `REFERENCES`
(resolved targets) and incoming references (what cites it)

### 2.6 `GET /health` / `GET /readyz`

Liveness vs. readiness (readiness pings Neo4j and the embedding service).
Both open endpoints used by the proxy health checks.

### 2.7 Admin (authenticated)

All `/v1/admin/*` routes require authorization. Mode is configuration-driven,
first configured wins (`civic/auth.py`):

1. **OIDC** (`OIDC_ISSUER`, optional `OIDC_AUDIENCE`): bearer JWT validated
   against the issuer's JWKS; token must carry a `civic-admin` role
   (`roles` claim or boolean claim). This is the production mode with the
   municipal IdP.
2. **Static token** (`ADMIN_TOKEN`): exact bearer match; for bootstrap and
   automation.
3. **Dev fallback**: nothing configured and `CIVIC_ENVIRONMENT=dev` - open,
   with a startup warning. Production with nothing configured fails closed.

| Endpoint | Purpose |
|---|---|
| `GET /v1/admin/pending` | Instruments awaiting the amendment review gate |
| `POST /v1/admin/instruments/{number}/publish` | Publish a pending instrument; body `{"effective_on": "YYYY-MM-DD"}` optional |
| `GET /v1/admin/audit?limit=` | Recent chat sessions (default 50, max 200) |
| `GET /v1/admin/audit/stats` | Totals by finish + latency p50/p95 |
| `GET /v1/admin/audit/{query_id}` | One full audit record (runbook RB-4) |

Failures return `401` problem+json with `WWW-Authenticate: Bearer`;
unknown resources `404`. The same operations are available offline via
`python -m civic.tools.publish` and `python -m civic.tools.audit`.

## 3. Error model

| HTTP | `code` | When |
|---|---|---|
| 400 | `invalid_request` | Schema violation; details in `errors[]` |
| 404 | `not_found` | Unknown instrument/article id |
| 422 | `question_too_short` / `unsupported_locale` | Chat-specific validation |
| 429 | `rate_limited` | Token-bucket per IP + per route; headers include `Retry-After` |
| 503 | `dependency_unavailable` | Embeddings or LLM down; chat degrades rather than errors when only the LLM is down |
| 500 | `internal` | Logged with request id; no internals leaked |

Example problem response:

```json
{
  "type": "https://civicgraph.example.org/errors/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "code": "rate_limited",
  "detail": "Chat limit is 20 requests per minute.",
  "request_id": "req_01J..."
}
```

## 4. Limits

| Limit | Value |
|---|---|
| Chat request rate | 20/min/IP burst 40 |
| Search request rate | 60/min/IP |
| Question length | 2000 chars |
| History length | 6 turns |
| SSE idle timeout | 30 s (proxy) |

Limits are intentionally conservative until abuse patterns are observed;
tune from telemetry, not speculation. Enforcement is token-bucket, in-memory
per API instance (`X-RateLimit-Remaining` on limited routes, `Retry-After` on
429); multi-instance deployments terminate limits at the proxy.

## 5. Versioning

URL-versioned (`/v1`). Additive changes (new fields, new event types) do not
bump the version; clients must ignore unknown fields/events. Breaking changes
ship as `/v2` alongside `/v1` for one deprecation window (minimum 90 days).

## 6. Example: minimal client

```python
import httpx, json

with httpx.stream("POST", "http://localhost:8000/v1/chat",
                  json={"question": "are backyard hives allowed?"}, timeout=60) as r:
    for line in r.iter_lines():
        if line.startswith("data: "):
            evt = json.loads(line[6:])
            # dispatch on event name carried by preceding 'event:' line in real parsers
            print(evt)
```

(The web client in `web/components/chat.tsx` implements the full parser.)
