# Kimi loop L25 — email adapter (IMAP read + SMTP draft, no auto-send)

## Review carry-forward

From L24 review (to be filled).

**Branch:** `feature/l25-email-adapter` from **`develop`**.

---

## Goal

Ship the first half of `brainstorm-april-13.md` §3a: email **read and draft**
capability, with no automatic sending. Send requires the confirmation
callbacks from L23, and even then is two-step (draft, then explicit
`email_send(draft_id)` with confirmation).

This enables the "morning triage" and "summarize my inbox" patterns without
introducing outbound mail risk.

Target version: **0.6.0** (minor — new platform-level capability).

---

## Scope

### §1 — `EmailAdapter` tool provider

`src/hestia/email/adapter.py` (new):

- Uses `imaplib` (stdlib) for IMAP reads; `email.message` for parsing.
- Uses `smtplib` (stdlib) for SMTP drafts; `IMAP APPEND` to Drafts folder.
- Reads credentials from `EmailConfig`.
- HTML sanitization via `bleach` or `html2text`; add as a dep pinned to
  recent minor.

### §2 — Tools registered

- `email_list(folder="INBOX", limit=20, unread_only=False)` — returns
  `{from, subject, date, snippet, message_id}`.
- `email_read(message_id)` — returns `{headers, body, attachments}`; body
  HTML-stripped + length-capped.
- `email_search(query, folder="INBOX")` — IMAP SEARCH syntax subset
  (FROM, SUBJECT, SINCE).
- `email_draft(to, subject, body, reply_to=None)` — creates a draft via
  IMAP APPEND, returns `draft_id`. `requires_confirmation=False` (drafts
  are private to the operator's account).
- `email_send(draft_id)` — `requires_confirmation=True`. Reads the draft,
  sends it via SMTP, moves the original to Sent. **Requires L23.**
- `email_move(message_id, folder)` — `requires_confirmation=False`.
- `email_flag(message_id, flag)` — `requires_confirmation=False`.

### §3 — Config

```python
@dataclass
class EmailConfig:
    imap_host: str
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""        # or app-password
    default_folder: str = "INBOX"
    max_fetch: int = 50
    sanitize_html: bool = True
    injection_scan: bool = True   # inherits from SecurityConfig
```

Document loading from `.email.secrets.py` (gitignored), same pattern as
`.matrix.secrets.py`.

### §4 — TrustConfig gates

- `TrustConfig.subagent_email_send: bool = False` — subagents can never
  trigger sends, even with confirmation; they can only list/read/draft.
- `TrustConfig.scheduler_email_send: bool = False` — same for cron.

### §5 — Tests

- Mock IMAP/SMTP servers (use `aiosmtpd`'s debugging server and `imaplib`
  against an in-memory stub).
- `tests/integration/test_email_roundtrip.py`: draft → list drafts →
  (optional) send via mock SMTP → verify in Sent.
- `tests/unit/test_email_sanitization.py`: HTML stripping, injection
  scanner interaction, oversize body truncation.

### §6 — Docs

- `docs/guides/email-setup.md` — walk through creating an app password
  (Gmail/Fastmail), populating `.email.secrets.py`, running the
  `hestia email check` diagnostic.
- README: new "Email" section linked from integrations.

## Acceptance criteria

1. `hestia email list --limit 5` works against a real IMAP account.
2. From Matrix, "summarize my unread email" triggers `email_list` +
   `email_read` chain and produces a reasonable summary.
3. `email_send(draft_id)` triggers the L23 confirmation flow and does not
   send without ✅.
4. HTML sanitization strips scripts/tracking pixels before entering context.
5. Injection scanner annotates email bodies when patterns match.

## Post-loop self-check

- [ ] Mypy/Ruff not regressed.
- [ ] Bumped to 0.6.0 with changelog entry.
- [ ] Handoff report written.
- [ ] `docs/guides/email-setup.md` linked from README.
