# ADR-017: Prompt-injection detection and network egress auditing

## Status

Accepted

## Context

Before email integration (L25) lands, inbound content becomes a primary vector for
prompt injection. Tool results from `http_get` and `web_search` can contain malicious
instructions that attempt to override the model's behavior. At the same time, operators
need visibility into where Hestia is sending data — both for security review and for
detecting anomalous egress patterns.

Two capabilities were needed:

1. **Lightweight injection scanning** on tool results before they enter the model context.
2. **Audit logging** of every outbound HTTP request with domain-level aggregation.

## Decision

### 1. Scanner is annotation-only, never blocking

`InjectionScanner` runs regex heuristics (known patterns + entropy) over tool result
content. On a hit, the content is wrapped with a `[SECURITY NOTE: ...]` prefix. The
model still sees the original data but is primed to treat it as untrusted.

Rationale: Blocking would create a denial-of-service vector (an attacker could craft
content that always triggers the scanner, breaking legitimate tool chains). Annotation
is safe-by-default — even a 100 % false-positive rate just makes the model more
cautious, which is acceptable.

### 2. Scanner lives in `security/` and is wired through `HestiaConfig`

A new `SecurityConfig` dataclass holds `injection_scanner_enabled`,
`injection_entropy_threshold`, and `egress_audit_enabled`. It is attached to
`HestiaConfig.security` so operators can tune or disable it in their config file.

Rationale: Security features should be discoverable and configurable in the same place
as other settings. A standalone module keeps the logic isolated and testable.

### 3. Egress recording uses context variables, not factory injection

`http_get` and `web_search` read the current `TraceStore` from a `ContextVar`
(`current_trace_store`) set by the orchestrator at the start of each turn. This avoids
changing every tool signature or converting `http_get` into a factory.

Rationale: Context variables are already used for `current_session_id`. Extending the
pattern to the trace store keeps the tool layer decoupled from the persistence layer.
The alternative — passing `trace_store` into every network tool's factory — would have
touched the CLI registration code for both tools and complicated testing.

### 4. Egress events get their own table, not a column on `traces`

`egress_events` is a separate table with `id, session_id, url, domain, status, size,
created_at`. Domain-level aggregation is computed with a `GROUP BY` query.

Rationale: Egress volume can be high (every HTTP request). Storing it in the traces
table would bloat turn-level records and make domain aggregation expensive. A separate
table with indexes on `domain` and `created_at` keeps queries fast.

### 5. `audit` becomes a group with `run` and `egress` subcommands

The existing `hestia audit` command is moved to `hestia audit run`. A new
`hestia audit egress --since=7d` subcommand prints domain-level statistics and flags
low-volume or first-time domains.

Rationale: `audit` is a natural umbrella for security-related reporting. Grouping keeps
the CLI organized and leaves room for future subcommands (e.g. `audit anomalies`).

## Consequences

### Positive

- **Injection risk is reduced** even before email integration ships.
- **Operator visibility** into network egress improves compliance and incident response.
- **Non-blocking design** means the scanner can be tuned aggressively without breaking
  legitimate workflows.

### Negative

- **Extra per-request overhead:** `record_egress` adds one async DB write per HTTP
  request. In practice this is negligible compared to network latency.
- **Entropy threshold tuning:** Operators may need to adjust `injection_entropy_threshold`
  if their use case involves legitimately high-entropy content (e.g. base64 payloads).

## Related

- `src/hestia/security/injection.py`
- `src/hestia/config.py`
- `src/hestia/persistence/trace_store.py`
- `src/hestia/tools/builtin/http_get.py`
- `src/hestia/tools/builtin/web_search.py`
- `src/hestia/orchestrator/engine.py`
- `src/hestia/cli.py`
