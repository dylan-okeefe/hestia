"""Email tools factory.

Tools are only registered when EmailConfig is populated (imap_host set).
"""

from __future__ import annotations

from typing import Any

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter
from hestia.tools.capabilities import EMAIL_SEND, NETWORK_EGRESS
from hestia.tools.metadata import tool


def make_email_tools(config: EmailConfig) -> list[Any]:
    """Build email tools bound to the configured adapter.

    Returns an empty list if ``config.imap_host`` is empty — caller should
    not register any email tools when unconfigured.
    """
    if not config.imap_host:
        return []

    adapter = EmailAdapter(config)

    @tool(
        name="email_list",
        public_description=(
            "List emails in a folder. Returns sender, subject, date, snippet, and message_id. "
            "Use this to get an overview of a mailbox without fetching full bodies."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "IMAP folder name (default: INBOX)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default: 20)",
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "Only return unread messages (default: False)",
                },
            },
        },
        max_inline_chars=6000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_list(
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = False,
    ) -> str:
        """List emails in a folder."""
        try:
            messages = await adapter.list_messages(
                folder=folder,
                limit=limit,
                unread_only=unread_only,
            )
        except Exception as exc:
            return f"email_list failed: {type(exc).__name__}: {exc}"
        if not messages:
            return "No messages found."
        lines = []
        for m in messages:
            lines.append(
                f"- [{m['message_id']}] {m['from']} | {m['subject']} | {m['date']}"
            )
        return "\n".join(lines)

    @tool(
        name="email_read",
        public_description=(
            "Read a single email by its IMAP UID (message_id). "
            "Returns headers, sanitized body text, and attachment list. "
            "Use email_list first to discover message IDs."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "IMAP UID of the message to read",
                },
            },
            "required": ["message_id"],
        },
        max_inline_chars=8000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_read(message_id: str) -> str:
        """Read a single email by IMAP UID."""
        try:
            result = await adapter.read_message(message_id)
        except Exception as exc:
            return f"email_read failed: {type(exc).__name__}: {exc}"
        headers = result["headers"]
        body = result["body"]
        attachments = result["attachments"]
        lines = [
            f"From: {headers['from']}",
            f"To: {headers['to']}",
            f"Subject: {headers['subject']}",
            f"Date: {headers['date']}",
            f"Message-ID: {headers['message_id']}",
            "",
            f"{body}",
        ]
        if attachments:
            lines.append("")
            lines.append("Attachments:")
            for att in attachments:
                lines.append(f"  - {att['filename']} ({att['content_type']})")
        return "\n".join(lines)

    @tool(
        name="email_search",
        public_description=(
            "Search emails in a folder using simplified IMAP syntax. "
            "Supported predicates: FROM:<addr>, SUBJECT:<text>, SINCE:<YYYY-MM-DD>. "
            "Returns a list of matching IMAP UIDs."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. 'FROM:alice@example.com SUBJECT:invoice'",
                },
                "folder": {
                    "type": "string",
                    "description": "IMAP folder to search (default: INBOX)",
                },
            },
            "required": ["query"],
        },
        max_inline_chars=4000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_search(query: str, folder: str = "INBOX") -> str:
        """Search emails using simplified query syntax."""
        try:
            uids = await adapter.search_messages(query, folder=folder)
        except Exception as exc:
            return f"email_search failed: {type(exc).__name__}: {exc}"
        if not uids:
            return "No matching messages found."
        return "Matching UIDs: " + ", ".join(uids)

    @tool(
        name="email_draft",
        public_description=(
            "Create an email draft via IMAP APPEND to the Drafts folder. "
            "Returns a draft_id (IMAP UID). Drafts are private to the operator's account."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject",
                },
                "body": {
                    "type": "string",
                    "description": "Plain-text body",
                },
                "reply_to": {
                    "type": "string",
                    "description": "Optional Reply-To address",
                },
            },
            "required": ["to", "subject", "body"],
        },
        max_inline_chars=2000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_draft(
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> str:
        """Create a draft email. Returns draft_id."""
        try:
            draft_id = await adapter.create_draft(
                to=to,
                subject=subject,
                body=body,
                reply_to=reply_to,
            )
        except Exception as exc:
            return f"email_draft failed: {type(exc).__name__}: {exc}"
        return f"Draft created with id: {draft_id}"

    @tool(
        name="email_send",
        public_description=(
            "Send a previously created email draft. Requires explicit user confirmation. "
            "The draft is read from IMAP Drafts, sent via SMTP, and moved to Sent."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "IMAP UID of the draft to send",
                },
            },
            "required": ["draft_id"],
        },
        max_inline_chars=2000,
        requires_confirmation=True,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[EMAIL_SEND, NETWORK_EGRESS],
    )
    async def email_send(draft_id: str) -> str:
        """Send a draft email. Requires confirmation."""
        try:
            result = await adapter.send_draft(draft_id)
        except Exception as exc:
            return f"email_send failed: {type(exc).__name__}: {exc}"
        return result

    @tool(
        name="email_move",
        public_description=(
            "Move an email to another IMAP folder (e.g. archive, trash)."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "IMAP UID of the message to move",
                },
                "folder": {
                    "type": "string",
                    "description": "Destination folder name",
                },
            },
            "required": ["message_id", "folder"],
        },
        max_inline_chars=2000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_move(message_id: str, folder: str) -> str:
        """Move an email to another folder."""
        try:
            result = await adapter.move_message(message_id, folder)
        except Exception as exc:
            return f"email_move failed: {type(exc).__name__}: {exc}"
        return result

    @tool(
        name="email_flag",
        public_description=(
            "Flag an email (mark read/unread/starred). "
            "Accepted flags: read, unread, starred."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "IMAP UID of the message",
                },
                "flag": {
                    "type": "string",
                    "description": "Flag to set: read, unread, starred",
                },
            },
            "required": ["message_id", "flag"],
        },
        max_inline_chars=2000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_flag(message_id: str, flag: str) -> str:
        """Flag an email."""
        try:
            result = await adapter.flag_message(message_id, flag)
        except Exception as exc:
            return f"email_flag failed: {type(exc).__name__}: {exc}"
        return result

    return [
        email_list,
        email_read,
        email_search,
        email_draft,
        email_send,
        email_move,
        email_flag,
    ]


def make_email_search_and_read_tool(adapter: EmailAdapter) -> Any:
    """Factory for the composite email_search_and_read tool.

    Returns ``None`` when the adapter is unconfigured so the caller can skip
    registration.
    """
    if not adapter.config.imap_host:
        return None

    @tool(
        name="email_search_and_read",
        public_description=(
            "Search emails and read matching messages in a single IMAP session. "
            "Returns a list of dicts with uid, from, subject, snippet, and body. "
            "SMTP send is unchanged — this tool is read-only."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query using simplified IMAP syntax. "
                        "Supported: FROM:<addr>, SUBJECT:<text>, SINCE:<YYYY-MM-DD>."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default: 5)",
                },
            },
            "required": ["query"],
        },
        max_inline_chars=8000,
        requires_confirmation=False,
        ordering="serial",
        tags=["email", "builtin"],
        capabilities=[NETWORK_EGRESS],
    )
    async def email_search_and_read(query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search emails and read matching messages in one IMAP round trip."""
        folder = adapter.config.default_folder
        results: list[dict[str, Any]] = []
        async with adapter.imap_session(folder=folder):
            uids = await adapter.search_messages(query, folder=folder)
            for uid in uids[:limit]:
                try:
                    msg = await adapter.read_message(uid)
                except Exception:
                    continue
                body = msg.get("body", "")
                snippet = body[:200] if len(body) > 200 else body
                results.append(
                    {
                        "uid": uid,
                        "from": msg["headers"].get("from", ""),
                        "subject": msg["headers"].get("subject", ""),
                        "snippet": snippet,
                        "body": body,
                    }
                )
        return results

    return email_search_and_read
