"""Email adapter using IMAP for read/draft and SMTP for send.

All blocking stdlib I/O is dispatched via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import email
import html
import imaplib
import re
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

import nh3

from hestia.config import EmailConfig


class EmailAdapterError(RuntimeError):
    """Raised when an email operation fails."""

    pass


class EmailAdapter:
    """Tool provider for IMAP read/search and SMTP/IMAP draft flow.

    Uses ``imaplib`` (stdlib) for IMAP reads; ``email.message`` for parsing.
    Uses ``smtplib`` (stdlib) for SMTP sends; ``IMAP APPEND`` to Drafts folder.
    """

    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # IMAP helpers
    # ------------------------------------------------------------------

    def _imap_connect(self) -> imaplib.IMAP4_SSL:
        if not self.config.imap_host:
            raise EmailAdapterError("imap_host is not configured")
        conn = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
        if not self.config.username or not self.config.password:
            raise EmailAdapterError("username and password are required for IMAP")
        ok, data = conn.login(self.config.username, self.config.password)
        if ok != "OK":
            raise EmailAdapterError(f"IMAP login failed: {ok}")
        return conn

    def _smtp_connect(self) -> smtplib.SMTP:
        if not self.config.smtp_host:
            raise EmailAdapterError("smtp_host is not configured")
        smtp = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
        smtp.starttls()
        if not self.config.username or not self.config.password:
            raise EmailAdapterError("username and password are required for SMTP")
        smtp.login(self.config.username, self.config.password)
        return smtp

    @staticmethod
    def _decode_header_value(value: str | bytes) -> str:
        """Decode RFC 2047 encoded header values."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _parse_address(self, addr: str) -> str:
        """Return a cleaned-from-angles email address or display name."""
        m = re.search(r"<([^>]+)>", addr)
        return m.group(1) if m else addr.strip()

    def _extract_body(
        self, msg: email.message.Message, max_chars: int = 8000
    ) -> tuple[str, list[dict[str, str]]]:
        """Extract plain-text body and attachment metadata from a message.

        Returns:
            (body_text, attachments_list)
        """
        body_parts: list[str] = []
        attachments: list[dict[str, str]] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    filename = part.get_filename() or "unnamed"
                    attachments.append({"filename": filename, "content_type": content_type})
                    continue
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body_parts.append(payload.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
                elif content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            html_text = payload.decode("utf-8", errors="replace")
                            body_parts.append(self._sanitize_html(html_text))
                    except Exception:
                        pass
        else:
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    text = payload.decode("utf-8", errors="replace")
                    if content_type == "text/html":
                        text = self._sanitize_html(text)
                    body_parts.append(text)
            except Exception:
                pass

        body = "\n".join(body_parts).strip()
        if len(body) > max_chars:
            body = body[:max_chars].rstrip() + "\n...[truncated]"
        return body, attachments

    def _sanitize_html(self, raw_html: str) -> str:
        """Strip HTML tags and decode entities."""
        if not self.config.sanitize_html:
            return raw_html
        cleaned: str = nh3.clean(raw_html, tags=set())
        return html.unescape(cleaned)

    def _fetch_headers(self, conn: imaplib.IMAP4_SSL, uid: str, folder: str) -> dict[str, Any]:
        """Fetch envelope headers for a single UID."""
        conn.select(folder)
        ok, data = conn.uid(
            "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
        )
        if ok != "OK" or not data or data[0] is None:
            raise EmailAdapterError(f"Failed to fetch headers for uid {uid}")

        raw_msg = b""
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                raw_msg = item[1]
                break

        msg = email.message_from_bytes(raw_msg)
        return {
            "from": self._decode_header_value(msg.get("From", "")),
            "subject": self._decode_header_value(msg.get("Subject", "")),
            "date": self._decode_header_value(msg.get("Date", "")),
            "message_id_header": self._decode_header_value(msg.get("Message-ID", "")),
        }

    def _fetch_full(self, conn: imaplib.IMAP4_SSL, uid: str, folder: str) -> email.message.Message:
        """Fetch full RFC822 message for a UID."""
        conn.select(folder)
        ok, data = conn.uid("FETCH", uid, "(RFC822)")
        if ok != "OK" or not data or data[0] is None:
            raise EmailAdapterError(f"Failed to fetch message uid {uid}")
        raw_msg = b""
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                raw_msg = item[1]
                break
        parsed = email.message_from_bytes(raw_msg)
        if not isinstance(parsed, email.message.Message):
            raise EmailAdapterError(f"Unexpected message type for uid {uid}")
        return parsed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_messages(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List messages in a folder.

        Returns list of dicts with keys: from, subject, date, snippet, message_id.
        ``message_id`` is the IMAP UID (numeric string).
        """

        def _run() -> list[dict[str, Any]]:
            conn = self._imap_connect()
            try:
                conn.select(folder)
                if unread_only:
                    ok, data = conn.uid("SEARCH", "UNSEEN")
                else:
                    ok, data = conn.uid("SEARCH", "ALL")
                if ok != "OK" or not data or data[0] is None:
                    return []
                uids = data[0].split()
                uids = uids[-limit:]  # most recent first

                results: list[dict[str, Any]] = []
                for uid in reversed(uids):  # newest first
                    uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                    try:
                        headers = self._fetch_headers(conn, uid_str, folder)
                        # Build a short snippet from subject
                        snippet = headers["subject"][:120]
                        results.append(
                            {
                                "from": self._parse_address(headers["from"]),
                                "subject": headers["subject"],
                                "date": headers["date"],
                                "snippet": snippet,
                                "message_id": uid_str,
                            }
                        )
                    except EmailAdapterError:
                        continue
                return results
            finally:
                conn.close()
                conn.logout()

        return await asyncio.to_thread(_run)

    async def read_message(self, message_id: str) -> dict[str, Any]:
        """Fetch full message body by IMAP UID.

        Returns dict with keys: headers, body, attachments.
        """

        def _run() -> dict[str, Any]:
            conn = self._imap_connect()
            try:
                conn.select(self.config.default_folder)
                msg = self._fetch_full(conn, message_id, self.config.default_folder)
                body, attachments = self._extract_body(msg)
                return {
                    "headers": {
                        "from": self._decode_header_value(msg.get("From", "")),
                        "to": self._decode_header_value(msg.get("To", "")),
                        "subject": self._decode_header_value(msg.get("Subject", "")),
                        "date": self._decode_header_value(msg.get("Date", "")),
                        "message_id": self._decode_header_value(msg.get("Message-ID", "")),
                    },
                    "body": body,
                    "attachments": attachments,
                }
            finally:
                conn.close()
                conn.logout()

        return await asyncio.to_thread(_run)

    async def search_messages(self, query: str, folder: str = "INBOX") -> list[str]:
        """Search messages using a simplified query syntax.

        Supports ``FROM:<addr>``, ``SUBJECT:<text>``, ``SINCE:<YYYY-MM-DD>``.
        Returns list of IMAP UIDs.
        """

        def _run() -> list[str]:
            conn = self._imap_connect()
            try:
                conn.select(folder)
                criteria = self._parse_search_query(query)
                ok, data = conn.uid("SEARCH", None, criteria)  # type: ignore[arg-type]
                if ok != "OK" or not data or data[0] is None:
                    return []
                uids = data[0].split()
                return [u.decode() if isinstance(u, bytes) else str(u) for u in uids]
            finally:
                conn.close()
                conn.logout()

        return await asyncio.to_thread(_run)

    @staticmethod
    def _parse_search_query(query: str) -> str:
        """Convert simplified query to IMAP SEARCH criteria."""
        parts: list[str] = []
        tokens = query.split()
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.upper().startswith("FROM:"):
                parts.append(f'FROM "{token[5:]}"')
            elif token.upper().startswith("SUBJECT:"):
                parts.append(f'SUBJECT "{token[8:]}"')
            elif token.upper().startswith("SINCE:"):
                date_str = token[6:]
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    imap_date = dt.strftime("%d-%b-%Y")
                    parts.append(f'SINCE "{imap_date}"')
                except ValueError:
                    parts.append(f'SUBJECT "{token}"')
            else:
                # Default: treat as subject search
                parts.append(f'SUBJECT "{token}"')
            i += 1
        if not parts:
            parts.append("ALL")
        return "(" + " ".join(parts) + ")"

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> str:
        """Create a draft via IMAP APPEND to the Drafts folder.

        Returns the new IMAP UID (draft_id).
        """

        def _run() -> str:
            conn = self._imap_connect()
            try:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = self.config.username
                msg["To"] = to
                if reply_to:
                    msg["Reply-To"] = reply_to
                msg["Date"] = email.utils.format_datetime(datetime.now(UTC))  # type: ignore[attr-defined]
                if "Message-ID" not in msg:
                    domain = self.config.username.split("@")[-1]
                    msg["Message-ID"] = email.utils.make_msgid(domain=domain)
                msg.set_content(body)

                raw = msg.as_bytes()
                conn.select("Drafts")
                ok, data = conn.append(
                    "Drafts",
                    None,
                    None,
                    raw,
                )
                if ok != "OK":
                    raise EmailAdapterError(f"Failed to append draft: {ok}")

                # Retrieve the UID of the appended message.  IMAP does not
                # return it directly, so we search for the most recent message
                # in Drafts with this Message-ID.
                mid = msg["Message-ID"]
                ok, data = conn.uid("SEARCH", None, f'HEADER Message-ID "{mid}"')  # type: ignore[arg-type]
                if ok == "OK" and data and data[0]:
                    uids = data[0].split()
                    if uids:
                        latest = uids[-1]
                        return latest.decode() if isinstance(latest, bytes) else str(latest)

                raise EmailAdapterError(
                    f"Created draft but could not locate it in Drafts by Message-ID {mid!r}"
                )
            finally:
                conn.close()
                conn.logout()

        return await asyncio.to_thread(_run)

    async def send_draft(self, draft_id: str) -> str:
        """Read a draft from IMAP Drafts, send via SMTP, move to Sent.

        Returns a status string.
        """

        def _run() -> str:
            if draft_id == "draft-unknown":
                raise EmailAdapterError(
                    "Cannot send draft with placeholder ID 'draft-unknown'"
                )
            # 1. Fetch draft
            imap = self._imap_connect()
            try:
                imap.select("Drafts")
                msg = self._fetch_full(imap, draft_id, "Drafts")

                # 2. Send via SMTP
                smtp = self._smtp_connect()
                try:
                    smtp.send_message(msg)
                finally:
                    smtp.quit()

                # 3. Copy to Sent, mark draft deleted
                imap.select("Drafts")
                imap.uid("COPY", draft_id, "Sent")
                imap.uid("STORE", draft_id, "+FLAGS", "(\\Deleted)")
                imap.expunge()

                to_addr = msg.get("To", "unknown")
                return f"Sent message to {to_addr} (draft {draft_id})"
            finally:
                imap.close()
                imap.logout()

        return await asyncio.to_thread(_run)

    async def move_message(self, message_id: str, folder: str) -> str:
        """Move a message to another folder."""

        def _run() -> str:
            conn = self._imap_connect()
            try:
                conn.select(self.config.default_folder)
                conn.uid("COPY", message_id, folder)
                conn.uid("STORE", message_id, "+FLAGS", r"(\Deleted)")
                conn.expunge()
                return f"Moved message {message_id} to {folder}"
            finally:
                conn.close()
                conn.logout()

        return await asyncio.to_thread(_run)

    async def flag_message(self, message_id: str, flag: str) -> str:
        """Set a flag on a message.

        Known flags: ``\\Seen``, ``\\Answered``, ``\\Flagged``, ``\\Deleted``.
        For operator convenience we also accept short aliases:
        ``read`` → ``\\Seen``, ``unread`` → unset ``\\Seen``,
        ``starred`` → ``\\Flagged``.
        """

        def _run() -> str:
            conn = self._imap_connect()
            try:
                conn.select(self.config.default_folder)
                flag_upper = flag.upper()
                if flag_upper in ("READ", "SEEN"):
                    imap_flag = "\\Seen"
                    action = "+FLAGS"
                elif flag_upper in ("UNREAD", "UNSEEN"):
                    imap_flag = "\\Seen"
                    action = "-FLAGS"
                elif flag_upper in ("STARRED", "FLAGGED"):
                    imap_flag = "\\Flagged"
                    action = "+FLAGS"
                else:
                    imap_flag = flag
                    action = "+FLAGS"

                conn.uid("STORE", message_id, action, f"({imap_flag})")
                return f"Flagged message {message_id} with {imap_flag} ({action})"
            finally:
                conn.close()
                conn.logout()

        return await asyncio.to_thread(_run)
