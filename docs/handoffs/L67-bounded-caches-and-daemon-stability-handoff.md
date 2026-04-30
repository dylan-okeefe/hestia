# L67 — Bounded Caches & Daemon Stability Handoff

**Branch:** `feature/l67-bounded-caches-and-daemon-stability`
**Status:** Complete, ready for review

## Changes

### §1 — `_tokenize_cache` LRU
- Replaced plain `dict` with `OrderedDict` bounded to 4096 entries
- Oldest entries evicted automatically

### §2 — `_last_edit_times` TTL
- Added `_prune_last_edit_times()` to `TelegramAdapter` with 1-hour TTL
- Called on every `edit_message()` invocation

### §3 — `_join_overhead` permanent cache
- `_join_overhead` is now set after first computation regardless of message count

### §4 — `list_dir` batching
- Already batched into single `asyncio.to_thread` call (no change needed)

### §5 — Static content token caching
- Added `_system_token_count` cache in `_count_body`
- Caches single system-message counts; invalidated when content changes

## Quality gates

- `pytest tests/unit/test_context_builder.py` — 13 passed
- `mypy src/hestia/context/builder.py src/hestia/platforms/telegram_adapter.py` — no issues
- `ruff check` — clean

## Intent verification

- **Memory is predictable:** 4096-entry cap prevents unbounded growth.
- **Telegram edit times don't leak:** 1-hour TTL evicts stale message IDs.
- **System prompt counted once per session:** Cache hit verified in `build()` flow.

## Next

Ready to merge to `develop` and start L68.
