# ADR-0025: Identity as a Compiled, Bounded, Operator-Owned Document

## Status

Accepted

## Context

Hestia needs a way to have a consistent personality across sessions. The personality should:
1. Be defined by the operator (not self-evolving)
2. Have bounded size (to preserve token budget and prefix cache efficiency)
3. Be separate from policy (personality != permissions)
4. Be stable within a session (for prefix cache efficiency)

Options considered:
- **Raw injection**: Inject the full soul.md into every system prompt. Rejected: unbounded size, pollutes context.
- **Embedded in config**: Store personality snippets in HestiaConfig. Rejected: mixes concerns, hard to edit.
- **Compiled identity view (chosen)**: Compile soul.md to a compact form on startup, cache it, prepend to system prompt. Bounded, operator-controlled, cache-friendly.

## Decision

We will implement a compiled identity view system with the following design:

### 1. soul.md Format

A markdown file describing Hestia's personality, tone, values, and anti-patterns. Example:

```markdown
# Personality

You are Hestia, a helpful AI assistant. You value clarity and conciseness.

## Tone

Warm but professional. Avoid excessive apologies.

## Anti-patterns

- Don't ask "How can I help you?" more than once per session.
- Don't over-explain simple operations.
```

### 2. IdentityConfig

```python
@dataclass
class IdentityConfig:
    soul_path: Path | None = None           # Path to soul.md (None = no personality)
    compiled_cache_path: Path = field(
        default_factory=lambda: Path(".hestia/compiled_identity.txt")
    )
    max_tokens: int = 300                   # Hard cap on compiled view size
    recompile_on_change: bool = True        # Recompile if soul.md changes
```

### 3. Compilation Strategy

**Deterministic extraction (default)**: Parse the markdown, extract text under each heading, concatenate as a flat text block, stripping markdown syntax. If over `max_tokens`, truncate from the bottom. No model call needed.

**Model-assisted compilation (future)**: Optional flag to send soul.md to the model for compression. Not implemented in Phase 8a.

### 4. Integration

The compiled identity view is prepended to the system prompt in ContextBuilder:

```
<compiled_identity>

<system_prompt>
```

This ensures the identity is always present and stable for the session (good for prefix caching).

### 5. Caching

The compiled result is cached to `.hestia/compiled_identity.txt` with format:
```
<sha256_hash>
truncated=<bool>
<compiled_text>
```

Recompilation occurs only when the source hash changes (if `recompile_on_change=True`).

## Consequences

### Positive

- **Bounded**: max_tokens caps the identity size (default 300 tokens ≈ 1200 chars).
- **Operator-owned**: soul.md is hand-authored, not machine-generated.
- **Cache-friendly**: Identity is frozen per session, enabling prefix cache hits.
- **Fast**: Deterministic extraction requires no model calls.

### Negative

- **Static within session**: Identity cannot change mid-session (by design).
- **Truncation risk**: Large soul.md documents are truncated from bottom (important content should go first).
- **One more file**: Users need to manage soul.md alongside config.

## Implementation

- `src/hestia/identity/compiler.py`: IdentityCompiler with deterministic extraction
- `src/hestia/config.py`: IdentityConfig added to HestiaConfig
- `src/hestia/context/builder.py`: Accepts optional identity_prefix parameter
- `src/hestia/cli.py`: Compiles identity on startup and sets it on ContextBuilder

## Related

- Phase 8.1 in docs/design/hestia-phase-8-plus-roadmap.md
