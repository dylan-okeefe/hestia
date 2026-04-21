"""Regression tests for Gmail folder names and IMAP close guard (L40)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter, EmailAdapterError


def _make_mock_imap(state: str = "SELECTED") -> tuple[MagicMock, MagicMock]:
    """Return (mock_class, mock_conn) with configurable IMAP state."""
    mock_conn = MagicMock()
    mock_conn.select.return_value = ("OK", [b"0"])
    mock_conn.close.return_value = ("OK", [])
    mock_conn.logout.return_value = ("OK", [b"BYE"])
    mock_conn.login.return_value = ("OK", [b"LOGIN completed"])
    mock_conn.state = state
    mock_conn.append.return_value = ("OK", [b"APPEND completed"])
    mock_conn.uid.return_value = ("OK", [b"42"])
    mock_cls = MagicMock(return_value=mock_conn)
    return mock_cls, mock_conn


class TestGmailFolderConfiguration:
    """Configurable drafts/sent folders for Gmail compatibility."""

    @pytest.mark.anyio
    async def test_create_draft_uses_configured_folder(self) -> None:
        """create_draft APPENDs to the configured drafts_folder."""
        mock_cls, mock_conn = _make_mock_imap()
        config = EmailConfig(
            imap_host="imap.gmail.com",
            username="u@gmail.com",
            password="p",
            smtp_host="smtp.gmail.com",
            drafts_folder="[Gmail]/Drafts",
            sent_folder="[Gmail]/Sent Mail",
        )
        adapter = EmailAdapter(config)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            draft_id = await adapter.create_draft(
                to="r@example.com",
                subject="S",
                body="B",
            )

        assert draft_id == "42"
        append_call = mock_conn.append.call_args
        assert append_call is not None
        folder = append_call.args[0]
        assert folder == "[Gmail]/Drafts"

    @pytest.mark.anyio
    async def test_send_draft_uses_configured_folders(self) -> None:
        """send_draft reads from drafts_folder and copies to sent_folder."""
        mock_cls, mock_conn = _make_mock_imap()
        config = EmailConfig(
            imap_host="imap.gmail.com",
            username="u@gmail.com",
            password="p",
            smtp_host="smtp.gmail.com",
            drafts_folder="[Gmail]/Drafts",
            sent_folder="[Gmail]/Sent Mail",
        )
        adapter = EmailAdapter(config)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            with patch("hestia.email.adapter.smtplib.SMTP") as mock_smtp:
                mock_smtp_inst = mock_smtp.return_value
                # C-6: starttls() now validated against (220, *).
                mock_smtp_inst.starttls.return_value = (220, b"Ready")
                result = await adapter.send_draft("123")

        assert "Sent message" in result
        # Verify COPY destination is the configured sent folder
        copy_call = mock_conn.uid.call_args_list
        copy_args = [c for c in copy_call if c.args[0] == "COPY"]
        assert len(copy_args) == 1
        assert copy_args[0].args[2] == "[Gmail]/Sent Mail"


class TestImapCloseGuard:
    """IMAP close() must be guarded to avoid errors in AUTH state."""

    @pytest.mark.anyio
    async def test_close_skipped_in_auth_state(self) -> None:
        """When conn.state is AUTH, close() is skipped and logout still runs."""
        mock_cls, mock_conn = _make_mock_imap(state="AUTH")
        config = EmailConfig(
            imap_host="imap.test",
            username="u",
            password="p",
        )
        adapter = EmailAdapter(config)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            async with adapter.imap_session():
                pass

        assert mock_conn.close.call_count == 0
        assert mock_conn.logout.call_count == 1

    @pytest.mark.anyio
    async def test_close_called_in_selected_state(self) -> None:
        """When conn.state is SELECTED, close() runs before logout."""
        mock_cls, mock_conn = _make_mock_imap(state="SELECTED")
        config = EmailConfig(
            imap_host="imap.test",
            username="u",
            password="p",
        )
        adapter = EmailAdapter(config)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            async with adapter.imap_session():
                pass

        assert mock_conn.close.call_count == 1
        assert mock_conn.logout.call_count == 1


class TestImapUidChronology:
    """M-7: list_messages must sort by INTERNALDATE, not IMAP SEARCH order."""

    @pytest.mark.anyio
    async def test_list_messages_sorts_newest_first_by_internaldate(self) -> None:
        """SEARCH returns UIDs in non-chronological order; INTERNALDATE wins.

        This simulates the real-world case a Copilot audit flagged: an IMAP
        server returns UIDs [7, 3, 9] from SEARCH ALL (valid per RFC, not
        actually date-ordered). list_messages must not rely on that order —
        it fetches INTERNALDATE per UID and sorts newest-first.
        """

        def _make_mock_conn() -> MagicMock:
            conn = MagicMock()
            conn.select.return_value = ("OK", [b"0"])
            conn.close.return_value = ("OK", [])
            conn.logout.return_value = ("OK", [b"BYE"])
            conn.login.return_value = ("OK", [b"LOGIN completed"])
            conn.state = "SELECTED"

            # SEARCH returns UIDs deliberately out of date order.
            # INTERNALDATE fetches return (in order) dates that should
            # produce final ranking: 9 (2026) > 3 (2024) > 7 (2022).
            internaldates = {
                b"7": b'"01-Jan-2022 00:00:00 +0000"',
                b"3": b'"01-Jan-2024 00:00:00 +0000"',
                b"9": b'"01-Jan-2026 00:00:00 +0000"',
            }
            headers_per_uid = {
                "7": (b"From: a@example.com\r\nSubject: Old\r\nDate: X\r\n\r\n"),
                "3": (b"From: b@example.com\r\nSubject: Mid\r\nDate: X\r\n\r\n"),
                "9": (b"From: c@example.com\r\nSubject: New\r\nDate: X\r\n\r\n"),
            }

            def mock_uid(cmd: str, *args: object) -> tuple[str, list]:
                c = cmd.upper()
                if c == "SEARCH":
                    return ("OK", [b"7 3 9"])  # deliberately shuffled
                if c == "FETCH":
                    uid = str(args[0])
                    spec = str(args[1]) if len(args) > 1 else ""
                    if "INTERNALDATE" in spec:
                        idate = internaldates[uid.encode()]
                        return ("OK", [(b"%s (INTERNALDATE " % uid.encode() + idate + b")",)])
                    body = headers_per_uid[uid]
                    return ("OK", [(b"%s (BODY[HEADER] {%d}" % (uid.encode(), len(body)), body)])
                return ("OK", [b""])

            conn.uid.side_effect = mock_uid
            return conn

        mock_conn = _make_mock_conn()
        mock_cls = MagicMock(return_value=mock_conn)
        adapter = EmailAdapter(
            EmailConfig(imap_host="imap.test", username="u", password="p")
        )

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            results = await adapter.list_messages(limit=10)

        message_ids = [r["message_id"] for r in results]
        assert message_ids == ["9", "3", "7"], (
            f"Expected INTERNALDATE-sorted order [9, 3, 7], got {message_ids} "
            "— list_messages is still relying on IMAP SEARCH order (M-7)."
        )


class TestSmtpConnectTls:
    """C-6 / T-5 / T-6: SMTP connection type + STARTTLS refusal paths."""

    @pytest.mark.anyio
    async def test_smtp_starttls_refusal_raises_email_adapter_error(self) -> None:
        """T-5: STARTTLS refused by server → EmailAdapterError, no login attempt.

        A server that answers STARTTLS with (554, b"Nope") must cause
        _smtp_connect to raise EmailAdapterError *before* credentials are
        sent, and close the transport. Regression for the pre-C-6 behavior
        that discarded the starttls() response and silently sent
        credentials over cleartext.
        """
        config = EmailConfig(
            imap_host="imap.test",
            username="u",
            password="p",
            smtp_host="smtp.test",
            smtp_port=587,  # plaintext + STARTTLS path
        )
        adapter = EmailAdapter(config)

        with patch("hestia.email.adapter.smtplib.SMTP") as mock_smtp:
            mock_inst = mock_smtp.return_value
            mock_inst.starttls.return_value = (554, b"Nope")
            with pytest.raises(EmailAdapterError) as excinfo:
                adapter._smtp_connect()

            assert "STARTTLS refused" in str(excinfo.value)
            assert "smtp.test" in str(excinfo.value)
            mock_inst.close.assert_called_once()
            mock_inst.login.assert_not_called()

    @pytest.mark.anyio
    async def test_smtp_port_465_uses_implicit_ssl(self) -> None:
        """T-6: port 465 routes through smtplib.SMTP_SSL and logs in directly.

        On implicit-TLS (SMTPS) there is no STARTTLS step — the transport
        is already encrypted at connect. Verify SMTP_SSL is used and
        starttls() is never called.
        """
        config = EmailConfig(
            imap_host="imap.test",
            username="u@example.com",
            password="secret",
            smtp_host="smtp.test",
            smtp_port=465,  # SMTPS
        )
        adapter = EmailAdapter(config)

        with (
            patch("hestia.email.adapter.smtplib.SMTP_SSL") as mock_ssl,
            patch("hestia.email.adapter.smtplib.SMTP") as mock_plain,
        ):
            mock_ssl_inst = mock_ssl.return_value
            result = adapter._smtp_connect()

            mock_ssl.assert_called_once_with("smtp.test", 465)
            mock_plain.assert_not_called()
            mock_ssl_inst.starttls.assert_not_called()
            mock_ssl_inst.login.assert_called_once_with("u@example.com", "secret")
            assert result is mock_ssl_inst
