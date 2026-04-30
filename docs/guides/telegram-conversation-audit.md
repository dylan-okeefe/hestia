# Telegram Conversation Audit Guide

## Purpose

Periodically audit Telegram (and Matrix) conversations to find issues, weirdness,
and deficiencies in the bot's behavior. This is how we catch problems users don't
explicitly report — bad tool usage, loops, formatting failures, missing context,
and subagent death spirals.

## Database

All conversation data lives in the runtime SQLite DB:

```
~/Hestia-runtime/runtime-data/hestia.db
```

Key tables:

| Table | What it tracks |
|-------|----------------|
| `sessions` | One row per user/chat session. `platform_user` is the Telegram user ID or group chat ID. |
| `messages` | Individual messages within a session (`role`: user/assistant/tool/system). |
| `turns` | One row per user turn. `iteration` counts model calls. `error` stores failure reason. |
| `turn_transitions` | State machine history for each turn (received → building_context → awaiting_model → executing_tools → ...). |
| `traces` | Summary row per turn: user input summary, tools called, tool call count, delegated flag, outcome (success/failed). |
| `failure_bundles` | Classified failures with severity, error message, and tool chain. |
| `egress_events` | Every outbound HTTP call (URL, domain, status, size). |

## Quick-start audit queries

Run these via Python (`PYTHONPATH=src uv run python`) or adapt to any SQLite
client. The DB uses `aiosqlite` format — standard SQLite, no special extensions.

### 1. Recent failures (always start here)

```python
"""
SELECT t.id, t.session_id, t.iteration, t.error, t.started_at
FROM turns t
JOIN sessions s ON t.session_id = s.id
WHERE s.platform = 'telegram'
  AND (t.iteration > 5 OR t.error IS NOT NULL)
ORDER BY t.started_at DESC
LIMIT 20
"""
```

**What to look for:**
- `iteration > 8` → likely a tool loop or subagent spiral.
- `error LIKE '%Max iterations%'` → hard limit hit; investigate what tools were called.
- `error LIKE '%Jinja%'` or `error LIKE '%System message%'` → prompt template bug.
- `error LIKE '%Chat completion failed%'` → inference server issue (check llama-server).

### 2. Failure bundles (pre-classified)

```python
"""
SELECT fb.id, fb.failure_class, fb.severity, fb.error_message, fb.tool_chain
FROM failure_bundles fb
JOIN sessions s ON fb.session_id = s.id
WHERE s.platform = 'telegram'
ORDER BY fb.created_at DESC
LIMIT 20
"""
```

**Classes you will see:**
- `max_iterations` → Turn burned all 10 iterations. Read the session messages.
- `inference_error` → Model/llama-server failure. Usually transient.
- `tool_error` → A specific tool threw. Check `tool_chain` for which one.

### 3. Traces (high-level turn summary)

```python
"""
SELECT t.user_input_summary, t.tools_called, t.tool_call_count,
       t.delegated, t.outcome, t.started_at
FROM traces t
JOIN sessions s ON t.session_id = s.id
WHERE s.platform = 'telegram'
ORDER BY t.started_at DESC
LIMIT 30
"""
```

**Red flags:**
- `tool_call_count >= 8` → excessive tool use for one user message.
- `delegated = 1 AND outcome = 'failed'` → subagent failed. Check if parent kept retrying.
- `tools_called` contains repeated calls to the same tool → loop.
- `tools_called` contains `http_get` with Google/Yelp URLs → bot ignoring `search_web`.

### 4. Read actual messages from a problematic session

```python
"""
SELECT idx, role, substr(content, 1, 200) as preview
FROM messages
WHERE session_id = '<SESSION_ID>'
ORDER BY idx
"""
```

For the full content of a specific message:

```python
"""
SELECT content FROM messages
WHERE session_id = '<SESSION_ID>' AND idx = <INDEX>
"""
```

### 5. Turn state transitions (loop diagnosis)

```python
"""
SELECT idx, from_state, to_state, at, reason
FROM turn_transitions
WHERE turn_id = '<TURN_ID>'
ORDER BY idx
"""
```

**Loop signature:** `awaiting_model` → `executing_tools` → `building_context`
repeating multiple times with no `awaiting_user_input` in between.

If you see `awaiting_subagent` → `executing_tools` repeating, that's a subagent
death spiral.

### 6. Egress audit (what URLs did the bot hit?)

```python
"""
SELECT url, domain, status, size, created_at
FROM egress_events
WHERE session_id = '<SESSION_ID>'
ORDER BY created_at
"""
```

**Red flags:**
- `domain = 'www.google.com'` or `domain = 'www.yelp.com'` with `status = 200`
  and `size > 50000` → bot downloaded a JS-heavy page with `http_get` instead
  of using `search_web` or Tavily.
- `domain = 'api.tavily.com'` with `status != 200` → Tavily API error.

## What to evaluate

For each problematic session, answer these questions:

### A. Tool usage
- Did the bot pick the right tool for the job?
  - Web search queries should use `search_web` (DuckDuckGo) or Tavily, NOT `http_get` on Google/Yelp.
  - File operations should use `read_file`/`write_file`, not `terminal` with `cat`.
  - Memory lookups should use `search_memory`, not raw `read_file` on the DB.
- Did the bot enter a retry loop? (same tool called repeatedly with slightly different args)
- Did subagents fail and the parent keep spawning new ones?

### B. Response quality
- Was the response accurate? (check facts against the tool results)
- Was it appropriately concise vs. detailed for the context?
- Did it acknowledge all parts of a multi-part user message?
- In group chats: did it address the right person?

### C. Formatting
- Bold/italic/code rendering correctly? (Should be HTML since the MarkdownV2 fix)
- Links clickable?
- Lists readable?

### D. Context/memory
- Did the bot remember previously shared info (names, locations, preferences)?
- Did it re-ask for info that was already in the conversation?
- Did compression/summary strategy drop critical context?

### E. Voice (if applicable)
- Did voice messages transcribe correctly?
- Was the voice reply sent as audio or did it fall back to text?
- If fallback: was the error logged?

## How to record findings

1. **Triage immediately if it's a code bug:**
   - Fix it in `src/hestia/` if you can.
   - Add/update tests.
   - Update the latest handoff doc (`docs/handoffs/L<NN>-...-handoff.md`).

2. **If it's a prompt/behavior issue:**
   - Update `SOUL.md` or the runtime system prompt in `config.runtime.py`.
   - Add a note to the active issues section of the latest handoff.

3. **If it's a user preference or memory gap:**
   - The bot should ideally store this via `make_save_memory_tool`. If it didn't,
     consider whether the memory tooling needs better prompting.

4. **Always update the handoff:**
   - Append a "Conversation audit findings" section to the most recent handoff.
   - Include session IDs, turn IDs, and a one-line summary of each issue found.

## Example audit session

```python
import aiosqlite
import asyncio

DB = "/home/dylan/Hestia-runtime/runtime-data/hestia.db"

async def audit():
    async with aiosqlite.connect(DB) as db:
        # Find high-iteration turns from today
        cursor = await db.execute("""
            SELECT t.id, t.session_id, t.iteration, t.error
            FROM turns t
            JOIN sessions s ON t.session_id = s.id
            WHERE s.platform = 'telegram'
              AND date(t.started_at) = date('now')
              AND t.iteration > 5
            ORDER BY t.iteration DESC
        """)
        for row in await cursor.fetchall():
            turn_id, session_id, iterations, error = row
            print(f"\n=== Turn {turn_id[:8]} | {iterations} iterations | {error or 'no error'} ===")

            # Show the user message that started this turn
            cur2 = await db.execute("""
                SELECT role, substr(content, 1, 120)
                FROM messages
                WHERE session_id = ?
                  AND idx = (SELECT MAX(idx) FROM messages WHERE session_id = ? AND role = 'user')
            """, (session_id, session_id))
            msg = await cur2.fetchone()
            if msg:
                print(f"User: {msg[1]}...")

            # Show egress URLs
            cur3 = await db.execute("""
                SELECT domain, status, size FROM egress_events
                WHERE session_id = ? ORDER BY created_at
            """, (session_id,))
            urls = await cur3.fetchall()
            if urls:
                print("URLs hit:")
                for domain, status, size in urls:
                    print(f"  {domain} [{status}] {size or 0} bytes")

asyncio.run(audit())
```

## Frequency

- **After any reported issue:** Immediate audit of the relevant session.
- **Weekly:** Run the quick-start queries to catch regressions.
- **After deployments:** Audit the first ~10 turns post-deployment.
