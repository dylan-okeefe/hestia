"""Concurrency tests for EmailAdapter IMAP operations (L221 §2)."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter, EmailAdapterError


def _make_adapter() -> EmailAdapter:
    return EmailAdapter(
        EmailConfig(
            imap_host="imap.test",
            username="user@test.com",
            password="secret",
            smtp_host="smtp.test",
        )
    )


def _make_tracking_mock(
    release: threading.Event,
) -> tuple[MagicMock, MagicMock, list[tuple[str, str]], threading.Event]:
    """Build a mock IMAP4_SSL that records command start/end order.

    Returns (mock_class, mock_conn, events, started_event).
    """
    events: list[tuple[str, str]] = []
    events_lock = threading.Lock()
    started = threading.Event()

    msg_bytes = (
        b"From: alice@example.com\r\n"
        b"Subject: Hello\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody text."
    )

    def mock_uid(cmd: str, *args: object) -> tuple[str, list]:
        with events_lock:
            events.append((cmd, "start"))
        started.set()
        release.wait(timeout=5.0)
        with events_lock:
            events.append((cmd, "end"))

        c = cmd.upper()
        if c == "SEARCH":
            return ("OK", [b"1"])
        if c == "FETCH":
            specifier = str(args[1]) if len(args) > 1 else ""
            if "RFC822" in specifier:
                return ("OK", [(b"1 (RFC822 {%d}" % len(msg_bytes), msg_bytes)])
            return ("OK", [(b"1 (BODY[HEADER] {%d}" % len(msg_bytes), msg_bytes)])
        if c == "STORE":
            return ("OK", [b"1"])
        if c == "COPY":
            return ("OK", [b"1"])
        return ("OK", [b""])

    mock_conn = MagicMock()
    mock_conn.select.return_value = ("OK", [b"0"])
    mock_conn.close.return_value = ("OK", [])
    mock_conn.logout.return_value = ("OK", [b"BYE"])
    mock_conn.login.return_value = ("OK", [b"LOGIN completed"])
    mock_conn.uid.side_effect = mock_uid

    mock_cls = MagicMock(return_value=mock_conn)
    return mock_cls, mock_conn, events, started


def _make_fast_mock() -> tuple[MagicMock, MagicMock]:
    """Return a mock IMAP4_SSL that returns immediately."""
    mock_conn = MagicMock()
    mock_conn.select.return_value = ("OK", [b"0"])
    mock_conn.close.return_value = ("OK", [])
    mock_conn.logout.return_value = ("OK", [b"BYE"])
    mock_conn.login.return_value = ("OK", [b"LOGIN completed"])
    mock_conn.uid.return_value = ("OK", [b"1"])
    mock_cls = MagicMock(return_value=mock_conn)
    return mock_cls, mock_conn


class TestEmailAdapterConcurrency:
    """Tests that EmailAdapter serializes concurrent IMAP operations."""

    @pytest.mark.anyio
    async def test_concurrent_imap_commands_do_not_interleave(self) -> None:
        """Two concurrent operations should not interleave IMAP commands."""
        release = threading.Event()
        mock_cls, _mock_conn, events, started = _make_tracking_mock(release)
        adapter = _make_adapter()

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            task1 = asyncio.create_task(adapter.search_messages("test"))
            task2 = asyncio.create_task(adapter.flag_message("1", "read"))

            # Wait for the first IMAP command to start inside the worker thread.
            await asyncio.to_thread(started.wait, 5.0)

            # With the lock held, the second operation must not have started yet.
            assert sum(1 for _, phase in events if phase == "start") == 1

            release.set()
            results = await asyncio.gather(task1, task2)

        assert results[0] == ["1"]
        assert results[1].startswith("Flagged message 1")

        # Total order must be start/end/start/end (no interleaving).
        assert len(events) == 4
        assert events[0][1] == "start"
        assert events[1][1] == "end"
        assert events[2][1] == "start"
        assert events[3][1] == "end"

    @pytest.mark.anyio
    async def test_lock_released_after_success(self) -> None:
        """The asyncio.Lock is released when an operation completes normally."""
        mock_cls, _mock_conn = _make_fast_mock()
        adapter = _make_adapter()

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls):
            await adapter.search_messages("test")

        assert not adapter._lock.locked()

    @pytest.mark.anyio
    async def test_lock_released_after_failure(self) -> None:
        """The asyncio.Lock is released even when an operation raises."""
        mock_cls, _mock_conn = _make_fast_mock()
        adapter = _make_adapter()

        with (
            patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_cls),
            pytest.raises(EmailAdapterError),
        ):
            await adapter.search_messages("SINCE:not-a-date")

        assert not adapter._lock.locked()
