# L53 — Tavily integration, Telegram HTML markdown, DuckDuckGo fallback handoff

## Scope

Production fixes for three active issues observed in the group chat:

1. **Web search failing** — Bot was attempting raw HTTP GET against Google/Yelp, getting JS-heavy pages with no parseable results, then entering subagent retry loops.
2. **Telegram markdown not rendering** — `**bold**` and other Markdown formatting sent as plain text because `parse_mode` was not set.
3. **Missing Tavily API key** — Hermes had Tavily configured but Hestia's runtime did not have the key wired.

## Files changed

### Production code

| File | Change |
|------|--------|
| `src/hestia/platforms/telegram_adapter.py` | Added `_md_to_tg_html()` helper: converts `**bold**` → `<b>`, `*italic*` → `<i>`, `` `code` `` → `<code>`, ```` ```lang\ncode\n``` ```` → `<pre>`. Escapes HTML entities. Updated `send_message()`, `send_error()`, and all voice-fallback `reply_text()` paths to use `parse_mode="HTML"`. |
| `src/hestia/tools/builtin/search_web.py` | **New.** DuckDuckGo HTML search fallback (`search_web`). No API key required. Parses `html.duckduckgo.com` results with regex, extracts real URLs from `uddg=` redirect wrappers, filters ads (`/y.js?ad_domain`), deduplicates by URL. |
| `src/hestia/tools/builtin/http_get.py` | Updated `public_description` to explicitly warn that it does NOT work on JS-heavy sites (Google Search, Google Maps, Yelp) and to use `search_web` for general web searches instead. |
| `src/hestia/app.py` | Registers `search_web` as fallback when Tavily `web_search` is not configured. |
| `src/hestia/context/compressed_summary_strategy.py` | Fixed Jinja "System message must be at the beginning" error by merging summary into existing system prompt instead of inserting a second `system` message at index 1. |
| `src/hestia/scheduler/engine.py` | Added loop safety fixes (scheduler stability improvements from concurrent session work). |

### Runtime config (~/Hestia-runtime, gitignored)

| File | Change |
|------|--------|
| `.env` | Added `TAVILY_API_KEY=tvly-dev-...` (extracted from `~/.hermes/.env`). |
| `config.runtime.py` | Enabled Tavily: `web_search=WebSearchConfig(provider="tavily", api_key=os.environ.get("TAVILY_API_KEY", ""))`. |

### Tests

| File | Change |
|------|--------|
| `tests/unit/test_telegram_adapter.py` | Updated `send_message`, `send_error`, `send_system_warning` assertions to expect `parse_mode="HTML"`. |
| `tests/unit/test_search_web_duckduckgo.py` | **New.** 8 tests for `_strip_tags`, `_unescape`, ad filtering, redirect extraction, deduplication, max_results clamping, empty results, HTML parsing edge cases, and http_get failure handling. |
| `tests/unit/test_telegram_markdown_html.py` | **New.** 14 tests for `_md_to_tg_html`: bold, italic, inline code, code blocks, HTML escaping, edge cases (asterisks in math, unmatched asterisks, emoji, nested elements). |
| `tests/unit/test_compressed_summary_strategy.py` | Updated to match refactored `CompressedSummaryStrategy` behavior (summary merged into system prompt). |

## Design decisions

1. **HTML over MarkdownV2** — Telegram's `"Markdown"` mode only supports `*bold*` (single asterisk), not `**bold**` (double). `"MarkdownV2"` requires escaping 15+ characters which is fragile with LLM output. `"HTML"` with a small markdown→HTML converter is the safest choice.

2. **DuckDuckGo HTML over Lite/JSON** — `html.duckduckgo.com` returns clean, parseable HTML without JavaScript. The regex-based parser is intentionally simple (~20 lines) because the HTML structure is stable. No external dependency needed (unlike `duckduckgo-search` PyPI package).

3. **Tavily as primary, DuckDuckGo as fallback** — `app.py` checks `make_web_search_tool(cfg.web_search)`; if Tavily is configured it registers that, otherwise falls back to `search_web`. This lets deployments opt into Tavily by setting the env var without code changes.

4. **Ad filter fix** — Original code checked for `duckduckgo.com/y.js?` but DuckDuckGo HTML uses relative URLs (`/y.js?ad_domain=...`). Changed to `"/y.js?" in real_url` so ad filtering works for both relative and absolute redirects.

## Verification

- **Tavily config:** `uv run python -c "..."` confirmed tool is created with provider="tavily" and api_key set.
- **Telegram tests:** 25 passed (adapter, confirmation, voice routing).
- **DuckDuckGo tests:** 8 passed.
- **Markdown HTML tests:** 14 passed.
- **Total affected:** 59 passed, 0 failed.
- **Services:** Both `hestia-telegram.service` and `hestia-matrix.service` restarted and active.
