"""Regression tests for Gmail folder names and IMAP close guard (L40)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter


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
