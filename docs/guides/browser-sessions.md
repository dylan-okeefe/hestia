# Browser Sessions

Hestia uses Playwright to browse JavaScript-heavy sites (LinkedIn, Indeed, ZipRecruiter, Built In, etc.). Some sites use Cloudflare or similar bot protection that blocks headless browsers. To get past this, Hestia stores per-domain browser session state (cookies + localStorage) under `~/.hestia/browser-sessions/`.

---

## Three ways to manage sessions

| Type | Interface | When to use |
|------|-----------|-------------|
| **Web dashboard** | Browser Sessions page | The easiest path. Stream a headless or headed browser from the web UI, log in interactively, and save the session with one click. |
| **Anonymous warmup** | `scripts/warmup_site_session.py` | Public sites that show a Cloudflare challenge but don't require login (Indeed, ZipRecruiter, Built In). |
| **Authenticated login** | `browser_login` tool | Sites where you have an account and need to be logged in (LinkedIn messaging, Gmail). Opens a visible browser window on the server. |

---

## Web dashboard (recommended)

Navigate to **Browser Sessions** in the web dashboard.

### For most sites (headless)
1. Click **+ New Session**.
2. Enter the URL (e.g. `https://linkedin.com/login`).
3. Click **Start Session**.
4. Interact with the site through the streamed browser window: click, type,
   scroll. Password fields are automatically detected and masked on mobile.
5. Click **Done** to save cookies and storage state.

### For bot-blocking sites (headed)
Sites like Indeed that detect headless browsers:
1. Click **+ New Session**.
2. Check **Headed browser** before starting.
3. This launches a real browser window on the server with full anti-detection.
4. Interact through the stream exactly like the headless path.
5. Click **Done** to save.

### Manage existing sessions
- **Authenticate** — re-open a saved session to refresh cookies.
- **Headed Stream** — same as Authenticate but with `headless=False`.
- **Headed Login** — opens a real browser window on the server display without
  streaming (useful as a fallback).
- **Check Now** — verify the session is still authenticated.
- **Delete** — remove stored cookies and metadata.

---

## Anonymous warmup (Cloudflare bypass)

Many job sites don't require an account to view listings, but Cloudflare will block a headless browser. The workaround is to open a **real headed browser** (via `xvfb-run`) once, let Cloudflare's challenge auto-resolve, and save the resulting cookies. Future headless calls reuse those cookies and skip the challenge.

### Warm up a site

```bash
cd ~/Hestia-runtime
source .venv/bin/activate
PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py indeed.com
PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py ziprecruiter.com
PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py builtin.com
```

What it does:
1. Opens a headed Chromium window in a virtual framebuffer (`xvfb-run`).
2. Navigates to the site's homepage.
3. Waits ~15s for Cloudflare's "Managed Challenge" to complete.
4. Saves cookies + storage state to `~/.hestia/browser-sessions/<domain>/`.

No login credentials are entered. The resulting session is **anonymous but verified**.

### Refresh stale sessions

Sessions expire when cookies age out or Cloudflare rotates its challenge. If `browser_get` starts returning `[BLOCKED] ...` again, just re-run the warmup script.

---

## Authenticated login

For sites that require an actual account (e.g. LinkedIn for messaging, Gmail for IMAP alternatives):

```bash
# Via the Hestia CLI
hestia tool browser_login --url https://linkedin.com/login
```

This opens a **visible** browser window (requires a real display or `xvfb-run`). Log in manually, then close the browser. The session is saved automatically.

With `xvfb-run` on a headless server:

```bash
cd ~/Hestia-runtime
source .venv/bin/activate
PYTHONPATH=src xvfb-run hestia tool browser_login --url https://linkedin.com/login
```

---

## How `browser_get` uses sessions

When a workflow node or tool calls `browser_get(url)`:

1. Extracts the domain from the URL.
2. Loads the saved session from `~/.hestia/browser-sessions/<domain>/`.
3. Launches a headless browser with that session injected.
4. Fetches the page, then **refreshes and re-saves** the session so it stays current.

If no session exists, `browser_get` still works — it just starts from a blank browser profile.

---

## Session storage layout

```
~/.hestia/browser-sessions/
├── linkedin_com/
│   ├── cookies.json          # HTTP cookies
│   └── storage_state.json    # cookies + localStorage + sessionStorage
├── indeed_com/
│   ├── cookies.json
│   └── storage_state.json
└── builtin_com/
    ├── cookies.json
    └── storage_state.json
```

`browser_get` prefers `storage_state.json` (more complete) and falls back to `cookies.json`.

---

## Known site behavior

| Site | Needs login? | Needs warmup? | Notes |
|------|-------------|---------------|-------|
| **LinkedIn** | No (public job pages) | No | Works headless with URL normalization. |
| **Built In** | No | No | Generally accessible. |
| **Indeed** | No | **Yes** | Search works; individual `viewjob` pages often blocked without fresh cookies. |
| **ZipRecruiter** | No | **Yes** | Homepage works; deeper pages may need warmup. |
| **Glassdoor** | No | Sometimes | Intermittent "Humans only" block. |
| **Dice** | No | Sometimes | Job-detail pages sometimes require session. |

---

## Troubleshooting

### "[BLOCKED] Cloudflare verification page"

The site's cookies have expired or the challenge has rotated. Re-run the warmup script:

```bash
PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py <domain>
```

### "Playwright is not installed"

```bash
cd ~/Hestia-runtime
source .venv/bin/activate
uv pip install playwright
playwright install chromium
```

### `xvfb-run: python: not found`

Use `python3` explicitly and activate the venv:

```bash
source .venv/bin/activate
PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py <domain>
```
