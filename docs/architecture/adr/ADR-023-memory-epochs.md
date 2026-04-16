# ADR-023: Memory Epochs — Compiled Prompt-Facing Views

## Status

Accepted

## Context

The memory system stores declarative memories (facts, notes, preferences) in a searchable store. The challenge is deciding when and how to include these memories in the prompt context.

### Problem

Without epochs, we have three bad options:

1. **No memory injection**: The model doesn't know about stored memories, defeating the purpose of long-term memory.

2. **Inject on every turn**: Every `save_memory` call would regenerate the memory view and invalidate the prefix cache. This destroys performance and makes token budgets unpredictable.

3. **Inject only on explicit recall**: The model must use `search_memory` to find relevant context, adding latency and complexity to every interaction.

### Requirements

- Memories should be available to the model without explicit tool calls
- The system prompt should remain stable for the session's lifetime (prefix cache efficiency)
- Token budget for memories should be predictable
- Memory writes (`save_memory`) should not trigger context regeneration

## Decision

Implement **memory epochs** — compiled snapshots of relevant memories that:

1. Are compiled once per session at controlled boundaries
2. Remain stable throughout the session (no mid-session updates)
3. Are included in the system message alongside identity and base prompt
4. Have a bounded size (configurable max_tokens, default 500)

### Refresh Triggers

Memory epochs are compiled at:
- New session start
- Slot restore from disk
- Explicit `/refresh` meta-command
- Session split (if/when implemented)

**NOT** refresh triggers:
- `save_memory` during a turn
- Any mid-turn event

### Assembly Order

The system message is assembled in this order:

1. Compiled identity view (from soul.md)
2. Compiled memory epoch
3. Base system prompt
4. (future: compact skill index)

### Data Model

```python
@dataclass
class MemoryEpoch:
    compiled_text: str        # The actual text included in the system message
    created_at: datetime
    memory_count: int         # How many memories were considered
    token_estimate: int       # Approximate token count
```

### Compilation Strategy

The `MemoryEpochCompiler` fetches:
1. Recent memories (last 30 days)
2. Tag-matched memories if session has relevant tags (future enhancement)

Then deduplicates, formats as a compact text block, and truncates to max_tokens.

## Consequences

### Positive

- **Prefix cache stability**: The system message stays frozen for the session
- **Token budget predictability**: Memory epoch size is bounded
- **Clear read/write boundaries**: Memory writes don't affect context
- **Simple mental model**: Users understand that memories are "baked in" at session start

### Negative

- **Stale memories**: Memories saved mid-session won't appear until next refresh
- **Fixed budget**: Even important new memories won't displace existing epoch content
- **Compilation cost**: Full-text search on session start adds latency

### Mitigations

- The `/refresh` meta-command allows users to manually refresh the epoch
- The 30-day recency filter keeps epochs fresh without being overwhelming
- Future: tag-based relevance scoring could improve memory selection

## Alternatives Considered

### Option A: Dynamic memory injection

Regenerate memory context on every `save_memory` call. Rejected because it invalidates prefix cache and makes token budgets unpredictable.

### Option B: No automatic injection

Require explicit `search_memory` calls. Rejected because it adds friction to common interactions and the model often forgets to search.

### Option C: Knowledge Router

Route memories through a sophisticated relevance engine. Deferred — see roadmap Phase 10 notes. Epochs solve the immediate problem with less complexity.

## Related

- Roadmap §10.1: Memory epochs specification
- ADR-022: Identity as compiled view (similar pattern)
- Future: Knowledge Router (Phase 12+)
