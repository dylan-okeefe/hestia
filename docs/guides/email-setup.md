# Email Setup Guide

Hestia can read your email via IMAP, draft replies, and (with explicit
confirmation) send them via SMTP.  This guide walks through creating an app
password, storing it in an environment variable, and running the connectivity
diagnostic.

---

## 1. Create an app password

### Gmail

1. Go to **Google Account → Security → 2-Step Verification** and enable it.
2. Return to **Security → App passwords**.
3. Select **Mail** and your device, then click **Generate**.
4. Copy the 16-character password (e.g. `abcd efgh ijkl mnop`).

### Fastmail

1. Go to **Settings → Privacy & Security → App Passwords**.
2. Click **New App Password**.
3. Give it a label (e.g. "Hestia") and select **Mail (IMAP/SMTP)**.
4. Copy the generated password.

---

## 2. Store the password in an environment variable

**Recommended:** set your app password in an environment variable so it never
lives in source control:

```bash
export EMAIL_APP_PASSWORD="abcd efgh ijkl mnop"
```

For Fastmail:

```bash
export EMAIL_APP_PASSWORD="your-app-password"
```

Load this in your shell profile, systemd service `Environment=` line, or
container secret so Hestia receives it at runtime.

---

## 3. Wire it into your `config.py`

Use `password_env` so Hestia resolves the password from the environment:

```python
from hestia.config import HestiaConfig, EmailConfig

config = HestiaConfig(
    email=EmailConfig(
        imap_host="imap.gmail.com",
        smtp_host="smtp.gmail.com",
        username="you@gmail.com",
        password_env="EMAIL_APP_PASSWORD",
    ),
    # ... rest of your config
)
```

> **Ephemeral testing only:** you can pass a plaintext `password=` string
> directly to `EmailConfig` for quick local experiments. Do **not** commit
> plaintext passwords to version control.

---

## 4. Run the diagnostic

```bash
hestia email check
```

You should see something like:

```
IMAP connection OK (imap.gmail.com:993)
Default folder: INBOX
Messages found: 42
```

If it fails, double-check:

- The app password is correct (not your regular account password).
- IMAP is enabled in your mail provider's settings.
- Two-factor authentication is on (required for Gmail app passwords).

---

## 5. Available tools

Once configured, the model sees these tools:

| Tool | What it does | Needs confirmation? |
|------|-------------|-------------------|
| `email_list` | List emails in a folder | No |
| `email_read` | Read a single email by UID | No |
| `email_search` | Search with FROM/SUBJECT/SINCE | No |
| `email_draft` | Create a draft in Drafts | No |
| `email_send` | Send a draft via SMTP | **Yes** |
| `email_move` | Move a message to another folder | No |
| `email_flag` | Mark read/unread/starred | No |

### Sending is two-step

1. The model calls `email_draft(to, subject, body)` — no confirmation needed.
2. The model calls `email_send(draft_id)` — this triggers the confirmation
   flow (✅/❌ on Telegram, reply on Matrix, or CLI prompt).

If no confirmation callback is available (e.g. scheduler), `email_send` is
blocked unless the trust profile explicitly allows it.

---

## 6. Security notes

- **HTML sanitization** is on by default. Email bodies are stripped of scripts
  and tracking pixels before entering the model context.
- **Injection scanning** runs automatically on all tool results, including
  email content. Hits are annotated, never blocked.
- **Subagents and scheduler** cannot trigger `email_send` by default. Enable
  with `TrustConfig.subagent_email_send = True` or
  `TrustConfig.scheduler_email_send = True` if you need this.

---

## Design rationale

The env-var-first credential pattern was introduced in **L29** (reliability and
secrets hygiene) and consolidated alongside the ADR migration in that loop. The
original email adapter design and IMAP/SMTP draft flow are documented in the
**L25 handoff**:
[`docs/handoffs/L25-email-adapter-read-and-draft-handoff.md`](../handoffs/L25-email-adapter-read-and-draft-handoff.md).

For the broader secrets-hygiene discussion, see the
[`L29 handoff`](../handoffs/L29-reliability-secrets-handoff.md).
