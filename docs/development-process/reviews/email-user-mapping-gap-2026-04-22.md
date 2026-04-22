# Email-to-user mapping — gap analysis

**Date:** 2026-04-22
**Requested:** "I want to make sure that the users framework somewhere has a way to understand which email belongs to which user, for when I forward things to it."

## Short answer

**It does not exist today.** The "users framework" built in L45a–c is `platform:platform_user` keying over `HestiaConfig.trust_overrides` plus the same key on every memory row. Email is a **tool** the LLM pulls (IMAP via `email_list` / `email_read`), not an **inbound platform adapter** that fires on received messages. So there is no code path where a forwarded email triggers a turn attributed to a particular user — there's no listener at all.

If the intent is "forward email to an address and have Hestia handle it on my behalf," that's a new feature. This doc spells out what's there, what's missing, and the minimal shape of the change.

## What exists (quickly)

| Piece | Where | What it does |
|-------|-------|--------------|
| `platform_user` identity ContextVars | `src/hestia/runtime_context.py` | Tracks which user triggered the current turn; set by orchestrator.process_turn. |
| `trust_overrides` | `HestiaConfig.trust_overrides: dict[str, TrustConfig]` | Keyed on `platform:platform_user`, resolved by `DefaultPolicyEngine._trust_for` (policy/default.py:182). |
| Memory scope | `src/hestia/memory/store.py` | Every row has `(platform, platform_user)`. `_get_user_scope()` reads from ContextVars. |
| Allow-lists | `src/hestia/platforms/allowlist.py` | Per-platform whitelist only. No cross-platform identity linking. |
| Email tool | `src/hestia/email/adapter.py` + `src/hestia/tools/builtin/email_tools.py` | IMAP read, SMTP send, IMAP draft. **No inbound listener.** Only invoked when the LLM calls `email_list`, `email_read`, etc. |

## What's missing for "forward email → attributed turn"

Four things, in rough order of how much effort each is:

### 1. An email inbound platform (not a tool)

Today, `email_list` is pull-only — the orchestrator doesn't poll for new mail unless the LLM decides to. For "forward an email to Hestia," there needs to be a listener that:

- polls IMAP INBOX on a tick (or uses IMAP IDLE for push),
- pulls new messages matching a filter (e.g. `To: hestia@<your-domain>` or `Subject: starts with "[hestia]"`),
- calls `on_message(platform_name="email", platform_user=<resolved>, text=<parsed body + subject>)`,
- marks the message `\\Seen` + moves it to a "processed" folder so it doesn't re-fire.

This is a ~150–250 line platform adapter implementing `Platform` (`platforms/base.py`) alongside `telegram_adapter.py`, plus a `run_email` entry in `platforms/runners.py`.

### 2. A `from_address → platform_user` mapping

The adapter needs to answer: *the email came from `alice@example.com` — who is that?* Two reasonable designs:

**Option A: `EmailConfig.address_map` (minimal)** — a dict on the existing email config:

```python
email=EmailConfig(
    ...,
    address_map={
        "dylanokeefedev@gmail.com": "email:dylan",
        "<wife's email>": "email:wife",
    },
)
```

The email platform adapter would look up `parseaddr(msg['From'])[1].lower()` in the map and use the value as `platform_user`. Unknown senders get dropped (allow-list default-deny, same as Telegram/Matrix). Trust overrides key on `email:dylan` etc.

**Pros:** two dozen lines of code, slots into existing `platform:platform_user` scheme, no schema change.
**Cons:** a given human has a separate memory scope per platform. Dylan-on-Telegram and Dylan-on-email can't see each other's memories.

**Option B: First-class `User` entity (bigger)** — a new `User` with stable UUID, each platform identity is a foreign key:

```python
@dataclass
class User:
    id: str
    display_name: str
    emails: tuple[str, ...] = ()
    telegram_user_ids: tuple[str, ...] = ()
    matrix_mxids: tuple[str, ...] = ()
    trust: TrustConfig = field(default_factory=TrustConfig.paranoid)
```

Adapters map their inbound identity to a `user.id` and memory/trust key on that. Dylan-on-Telegram and Dylan-on-email share a scope.

**Pros:** identity unification works across platforms. More natural model for "Hestia knows me across channels."
**Cons:** schema migration on memory (drop `platform_user`, add `user_id`), migration on `trust_overrides` (key on `user_id` not `platform:platform_user`), changes to every adapter, docs updates. This is L45a-c again but one layer up.

**Recommendation:** Start with Option A. It unblocks the "forward email to Hestia" use case with minimal churn. If you later find memory isolation between channels annoying, promote to Option B as a deliberate L-loop (L48+, after the v0.10.0 release).

### 3. Authentication that a forwarded email is really from you

Forwarding emails through ISPs is easy to spoof at the `From:` header level. If the inbound adapter trusts `From:` without any cryptographic anchor, anyone who knows your forwarding address can impersonate you. Mitigations, weakest to strongest:

- **Plus-addressing token.** Send to `hestia+<secret>@yourdomain` and require the token. Bot ignores mail that doesn't match.
- **DKIM check on receipt.** The IMAP-retrieved `Authentication-Results:` header (set by your receiving MTA, typically Gmail/Fastmail/ProtonMail) has `dkim=pass`. Reject anything that isn't `dkim=pass` AND whose signing domain isn't in an allow-list (`gmail.com`, your domain). This is ~30 lines with Python's `email.headerregistry.HeaderRegistry` + a regex, assuming your MTA already validates.
- **S/MIME or PGP signature.** Overkill unless you're threat-modeling nation-state attackers.

**Recommendation:** Plus-addressing + DKIM check. Both cheap, compose well.

### 4. Forwarding-preservation parsing

When you "forward" an email in most clients, the original `From:` / `To:` / `Subject:` / body become quoted content inside the forwarded message. If Dylan wants attribution *to the original sender*, the email body parser needs to recognize forwarding patterns (`---------- Forwarded message ---------`, `Begin forwarded message:`, RFC 2822 `Resent-From:` header). If Dylan's use case is only "I forward my own mail to trigger Hestia to act on it," this is out of scope — `From:` is Dylan, full stop, the forwarded content is payload. Clarify before designing.

## Loop shape

If you want this next after README + Kimi review, the L47 spec is roughly:

```
L47 — Email inbound adapter + address map
§0  Security: default-deny; plus-addressing token; DKIM allow-list.
§1  EmailConfig.address_map: dict[str, str] = {}
§2  platforms/email_adapter.py — Platform impl with IMAP poll loop.
§3  platforms/runners.py — run_email(app, config).
§4  CLI: hestia run --platform email.
§5  Tests: address lookup, unknown-sender rejection, DKIM bypass rejection,
      seen/move semantics, re-entrancy (bot doesn't reply to its own sent mail).
§6  Docs: docs/guides/email-setup.md gets an "inbound" section.
```

Estimate: ~1 Kimi loop, ~400 LOC + tests.

## Where the current email tool still fits

`email_list` / `email_read` / `email_draft` / `email_send` remain useful even after an inbound adapter exists — they are how the LLM *acts* on your mailbox (reply, search history, compose). The inbound adapter is how Hestia *reacts* to new mail. The two are complementary, not overlapping.

## Sources

- `src/hestia/config.py:94` — `TelegramConfig` (template for any new adapter config).
- `src/hestia/config.py:599` — `HestiaConfig.trust_overrides`.
- `src/hestia/policy/default.py:182` — `_trust_for(session)`.
- `src/hestia/platforms/base.py` — `Platform` ABC.
- `src/hestia/email/adapter.py` — IMAP/SMTP transport.
- `src/hestia/tools/builtin/email_tools.py` — tool factory (tools only, no listener).
- `docs/handoffs/L45a-trust-identity-plumbing-handoff.md` — existing identity plumbing.
- `docs/guides/multi-user-setup.md` — current multi-user story (platform-scoped).
