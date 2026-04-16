# ADR-024: Skills as User-Defined Python Functions

## Status

Accepted

## Context

Hestia needs a way for users to define reusable multi-step workflows. These "skills" represent procedural memory — knowledge of *how to do things* rather than declarative facts. The key requirements are:

1. Users must be able to define skills without modifying core Hestia code
2. Skills need a lifecycle to manage trust (draft → tested → trusted → deprecated → disabled)
3. The model needs to know which skills are available without the full implementation being in context
4. Skills should be persisted and tracked across sessions

The alternative of automatic skill mining (discovering patterns from traces) was considered but deferred. There isn't enough usage data yet to make mining useful, and the infrastructure for testing and validating automatically-discovered skills doesn't exist.

## Decision

Skills are implemented as user-authored Python functions using a `@skill` decorator. Key aspects:

### 1. Skill Definition Format

Skills are Python files in a discoverable location, decorated with `@skill`:

```python
from hestia.skills import skill, SkillState, SkillContext, SkillResult

@skill(
    name="daily_briefing",
    description="Fetch weather, calendar, and news, then summarize.",
    required_tools=["http_get", "search_memory"],
    capabilities=["network_egress", "memory_read"],
    state=SkillState.DRAFT,
)
async def daily_briefing(context: SkillContext) -> SkillResult:
    weather = await context.call_tool("http_get", url="https://wttr.in/?format=3")
    memories = await context.call_tool("search_memory", query="morning routine")
    return SkillResult(
        summary=f"Weather: {weather}\nRelevant memories: {memories}",
        status="success",
    )
```

### 2. Skill Lifecycle States

```
DRAFT → TESTED → TRUSTED
  ↓       ↓        ↓
DISABLED ← DEPRECATED
```

- **DRAFT**: Initial state, under development
- **TESTED**: Has been run successfully at least once
- **TRUSTED**: Approved for general use
- **DEPRECATED**: Should not be used for new work, but still works
- **DISABLED**: Cannot be invoked

### 3. Skill Index in Prompt

The model sees only a compact index, not full skill bodies:

```
Available skills:
- daily_briefing: Fetch weather, calendar, and news, then summarize. [trusted, network_egress+memory_read]
- weekly_review: Summarize this week's activity from traces. [draft, memory_read]

To run a skill, use: run_skill(name="skill_name")
```

This keeps the context small while informing the model what's available.

### 4. Persistence

Skills are stored in a SQLite table with:
- id, name, description, file_path
- state (draft/tested/trusted/deprecated/disabled)
- capabilities and required_tools (JSON)
- created_at, last_run_at, run_count, failure_count

The file_path references the Python file containing the skill implementation. The skill decorator metadata is synchronized to the database on discovery.

### 5. CLI Commands

```
hestia skill list                   # list skills with states
hestia skill show NAME              # show skill details
hestia skill promote NAME           # advance state (draft→tested→trusted)
hestia skill demote NAME            # move back one state
hestia skill disable NAME           # disable without removing
hestia skill test NAME              # run skill in sandbox mode
```

## Consequences

### Positive

1. **User control**: Skills are explicitly authored, reviewed, and promoted by users
2. **Trust boundaries**: The lifecycle states make it clear which skills are production-ready
3. **Context efficiency**: The model only sees an index, not full implementations
4. **Persistence**: Skill state survives restarts and is queryable for analytics
5. **Testable**: Skills are Python functions that can be unit tested independently

### Negative

1. **Manual effort**: Users must write and maintain skills themselves
2. **Discovery gap**: Without automatic mining, users may not realize which workflows could be skills
3. **File management**: Skills in files need to be tracked, versioned, and deployed

### Deferred

Automatic skill mining (analyzing traces to discover candidate skills) is explicitly deferred until:
- The trace store has 30+ days of real usage data
- There's infrastructure for replaying traces to test skill proposals
- The manual skill lifecycle has proven valuable

## Related

- Phase 12 implementation: `docs/design/hestia-phase-8-plus-roadmap.md` §12.1–§12.5
- Skill types: `src/hestia/skills/`
- Skill persistence: `src/hestia/persistence/skill_store.py`
