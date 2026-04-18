"""Regression tests for IMAP session reuse via ContextVar (L33b)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter


def _make_mock_imap() -> tuple[MagicMock, MagicMock]:
    """Return (mock_class, mock_instance) with enough behaviour for list/read."""
    msg_bytes = (
        b"From: alice@example.com\r\n"
        b"Subject: Hello\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody text."
    )

    def mock_uid(cmd: str, *args: object) -> tuple[str, list]:
        c = cmd.upper()
        if c == "SEARCH":
            return ("OK", [b"1"])
        if c == "FETCH":
            specifier = str(args[1]) if len(args) > 1 else ""
            if "RFC822" in specifier:
                return ("OK", [(b"1 (RFC822 {%d}" % len(msg_bytes), msg_bytes)])
            return ("OK", [(b"1 (BODY[HEADER] {%d}" % len(msg_bytes), msg_bytes)])
        return ("OK", [b""])

    mock_conn = MagicMock()
    mock_conn.select.return_value = ("OK", [b"0"])
    mock_conn.close.return_value = ("OK", [])
    mock_conn.logout.return_value = ("OK", [b"BYE"])
    mock_conn.login.return_value = ("OK", [b"LOGIN completed"])
    mock_conn.uid.side_effect = mock_uid

    mock_cls = MagicMock(return_value=mock_conn)
    return mock_cls, mock_conn


class TestSessionReuse:
    """Unit tests for EmailAdapter.imap_session() ContextVar reuse."""

    @pytest.mark.anyio
    async def test_session_uses_single_connection(self) -> None:
        """Inside one outer imap_session(), list + read share one connection."""
        mock_cls, mock_conn = _make_mock_imap()
        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            adapter = EmailAdapter(
                EmailConfig(imap_host="imap.test", username="u", password="p")
            )
            async with adapter.imap_session():
                await adapter.list_messages(limit=5)
                await adapter.read_message("1")

        assert mock_cls.call_count == 1
        assert mock_conn.logout.call_count == 1

    @pytest.mark.anyio
    async def test_session_closes_on_exception(self) -> None:
        """Logout is still called when the async-with body raises."""
        mock_cls, mock_conn = _make_mock_imap()
        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            adapter = EmailAdapter(
                EmailConfig(imap_host="imap.test", username="u", password="p")
            )
            with pytest.raises(ValueError, match="boom"):
                async with adapter.imap_session():
                    raise ValueError("boom")

        assert mock_conn.logout.call_count == 1

    @pytest.mark.anyio
    async def test_nested_session_reuses_outer(self) -> None:
        """Two nested imap_session() blocks result in a single connection."""
        mock_cls, mock_conn = _make_mock_imap()
        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            adapter = EmailAdapter(
                EmailConfig(imap_host="imap.test", username="u", password="p")
            )
            async with adapter.imap_session() as outer:
                async with adapter.imap_session() as inner:
                    assert outer is inner

        assert mock_cls.call_count == 1
        assert mock_conn.logout.call_count == 1

    @pytest.mark.anyio
    async def test_no_outer_session_each_method_opens_own(self) -> None:
        """Without an outer imap_session(), each call gets its own connection."""
        mock_cls, mock_conn = _make_mock_imap()
        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            adapter = EmailAdapter(
                EmailConfig(imap_host="imap.test", username="u", password="p")
            )
            await adapter.list_messages(limit=5)
            await adapter.list_messages(limit=5)

        assert mock_cls.call_count == 2
        assert mock_conn.logout.call_count == 2
