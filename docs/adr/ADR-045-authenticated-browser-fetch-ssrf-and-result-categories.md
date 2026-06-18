# ADR-045: Authenticated browser fetch, SSRF guard, and structured result categories

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** `browser_get`/`browser_get_links` launched a fresh, cookieless
  Playwright context on every call, which is exactly the fingerprint bot
  detection waits for, so authenticated sites (LinkedIn, Indeed) timed out. The
  browser path also had no SSRF guard. Separately, tool failures were classified
  by scanning human-readable strings, which misfired on legitimate content that
  happened to contain words like "login" or "404" (L218/L222).

- **Decision:**
  1. A shared fetch helper (`tools/browser/fetch.py`) reuses persistent
     authenticated session storage per domain, applies the stealth layer, and
     rate-limits per domain. Page classification (login/challenge/404) is driven
     by the final URL, HTTP status, and title first; body text only triggers
     `BLOCKED` when login phrases dominate, so a job listing that says "log in to
     apply" is not discarded.
  2. SSRF guard (`security/ssrf.py` `assert_url_safe`) rejects loopback,
     link-local, cloud-metadata (169.254.169.254), and private ranges before
     `page.goto`; shared with `http_get`.
  3. Tool results carry structured `[CATEGORY: ...]` markers
     (`result_classifier.py`: `SUCCESS`, `TIMEOUT`, `BLOCKED`, `NOT_FOUND`,
     `TRANSIENT_OTHER`). Retry logic prefers the explicit marker over keyword
     scanning, caps retries of failed identical calls, fails fast on
     `BLOCKED`/`NOT_FOUND`, and escalates timeouts under per-attempt and
     total-per-URL time budgets.

- **Consequences:** Authenticated sites fetch reliably; the gate and retry logic
  consume the structured category rather than re-deriving it. Injection-flagged
  pages still escalate via ADR-043. A login/challenge page is its own failure
  class that prompts re-auth rather than being treated as content.

- **Related:** ADR-017, ADR-042, ADR-043; `tools/browser/fetch.py`,
  `security/ssrf.py`, `tools/result_classifier.py`.
