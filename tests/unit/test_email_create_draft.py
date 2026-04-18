"""Regression tests for email draft Message-ID and UID lookup (§3 L28)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from hestia.email.adapter import EmailAdapter, EmailAdapterError, EmailConfig


class TestCreateDraft:
    """Tests for create_draft Message-ID generation and UID retrieval."""

    def _make_adapter(self) -> EmailAdapter:
        return EmailAdapter(
            EmailConfig(
                imap_host="imap.test",
                username="user@test.com",
                password="secret",
                smtp_host="smtp.test",
            )
        )

    def _mock_imap(self, search_result: tuple[str, list[bytes]]) -> MagicMock:
        """Build a mock IMAP4_SSL that returns the given SEARCH result."""
        mock_imap_cls = MagicMock()
        mock_conn = mock_imap_cls.return_value
        mock_conn.login.return_value = ("OK", [b"LOGIN completed"])
        mock_conn.select.return_value = ("OK", [b"0"])
        mock_conn.append.return_value = ("OK", [b"APPEND completed"])
        mock_conn.uid.return_value = search_result
        mock_conn.close.return_value = ("OK", [b"CLOSE completed"])
        mock_conn.logout.return_value = ("OK", [b"BYE"])
        return mock_imap_cls

    def test_create_draft_assigns_message_id(self) -> None:
        adapter = self._make_adapter()
        mock_imap_cls = self._mock_imap(("OK", [b"42"]))

        async def _run() -> None:
            with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls):
                draft_id = await adapter.create_draft(
                    to="recipient@test.com",
                    subject="Test subject",
                    body="Hello",
                )
            assert draft_id == "42"
            # Verify append was called with bytes containing Message-ID
            append_call = mock_imap_cls.return_value.append.call_args
            assert append_call is not None
            _folder, _flags, _date, raw_bytes = append_call.args
            assert b"Message-ID:" in raw_bytes

        asyncio.run(_run())

    def test_create_draft_returns_real_uid_when_search_succeeds(self) -> None:
        adapter = self._make_adapter()
        mock_imap_cls = self._mock_imap(("OK", [b"42"]))

        async def _run() -> None:
            with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls):
                draft_id = await adapter.create_draft(
                    to="recipient@test.com",
                    subject="Test",
                    body="Body",
                )
            assert draft_id == "42"

        asyncio.run(_run())

    def test_create_draft_raises_when_search_misses(self) -> None:
        adapter = self._make_adapter()
        mock_imap_cls = self._mock_imap(("OK", [b""]))

        async def _run() -> None:
            with (
                patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls),
                pytest.raises(EmailAdapterError) as exc_info,
            ):
                await adapter.create_draft(
                    to="recipient@test.com",
                    subject="Test",
                    body="Body",
                )
            assert "draft-unknown" not in str(exc_info.value)
            assert "Message-ID" in str(exc_info.value)

        asyncio.run(_run())


class TestSendDraft:
    """Tests for send_draft guard against placeholder IDs."""

    def test_send_draft_rejects_draft_unknown(self) -> None:
        adapter = EmailAdapter(
            EmailConfig(
                imap_host="imap.test",
                username="user@test.com",
                password="secret",
                smtp_host="smtp.test",
            )
        )

        async def _run() -> None:
            with pytest.raises(EmailAdapterError) as exc_info:
                await adapter.send_draft("draft-unknown")
            assert "draft-unknown" in str(exc_info.value)

        asyncio.run(_run())
