# ADR-021: ContextBuilder Prefix Registry and Tokenize Cache

## Status

Accepted (registry in v0.7.7, cache in v0.7.8)

## Context

`ContextBuilder.build()` historically carried four parallel prefix conditionals
(`identity_prefix`, `memory_epoch_prefix`, `skill_index_prefix`, `style_prefix`)
as optional kwargs, concatenated in a hard-coded order. Adding a fifth prefix
required changing the signature, the assembly block, and every call site.

Simultaneously, the history-trim loop issued one `/tokenize` HTTP call per
candidate message — O(N) round trips for a turn with N historical messages.
For a 200-turn session this meant 200 POSTs to the llama-server before
inference could begin.

## Decision

1. **Prefix layers are an ordered registry.**  A private `_PrefixLayer` dataclass
   holds `(name, value)` pairs.  `_prefix_layers()` returns them in canonical
   order; `build()` assembles the effective system prompt with a single
   comprehension.  Setters (`set_identity_prefix`, etc.) mutate the registry
   without invalidating the message cache.

2. **Per-message token counts are content-keyed cached for the builder lifetime.**
   The cache key is `(message.role, message.content)`.  It survives across
   `build()` calls on the same instance.  If the inference client URL or model
   changes, callers construct a new `ContextBuilder`.

3. **Trim loop uses cached sums + a constant join-overhead.**  Instead of
   POSTing the concatenated candidate string each iteration, the loop sums
   cached per-message counts and adds `(len(window) - 1) * join_overhead`.
   The join overhead is measured once per build by comparing a two-message
   request body against a single-message body.  Acceptable error: ±1 token.

## Consequences

- **~99% fewer tokenize calls** on a typical session (from O(N) to O(1) per
  build for unchanged messages).
- **Adding a new prefix layer** is now one line in `_prefix_layers()` plus one
  setter — no signature or call-site changes.
- **The cache assumes message content is treated as immutable by callers.**
  Mutating a `Message` object in-place after it has been cached would produce
  stale counts.  This aligns with the existing convention that messages are
  value objects.
- **No reactive invalidation logic** was added.  The builder is intentionally
  simple: cache lives as long as the instance.
