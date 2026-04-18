"""Integration test for email_search_and_read composite tool (L33b)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter
from hestia.tools.builtin.email_tools import make_email_search_and_read_tool


@pytest.fixture
def config() -> EmailConfig:
    return EmailConfig(
        imap_host="imap.test",
        imap_port=993,
        smtp_host="smtp.test",
        smtp_port=587,
        username="user@test",
        password="secret",
        default_folder="INBOX",
    )


class FakeIMAP:
    """In-memory fake IMAP server for a single test run."""

    def __init__(self) -> None:
        self._folders: dict[str, dict[str, bytes]] = {}
        self._selected: str = ""
        self._uid_counter = 100

    def _ensure_folder(self, name: str) -> dict[str, bytes]:
        if name not in self._folders:
            self._folders[name] = {}
        return self._folders[name]

    def select(self, folder: str) -> tuple[str, list]:
        self._selected = folder
        return ("OK", [b"0"])

    def close(self) -> tuple[str, list]:
        self._selected = ""
        return ("OK", [])

    def logout(self) -> tuple[str, list]:
        return ("OK", [b"BYE"])

    def login(self, user: str, password: str) -> tuple[str, list]:
        return ("OK", [b"LOGIN completed"])

    def append(self, folder: str, *args: object) -> tuple[str, list]:
        msg_bytes = args[-1]
        if isinstance(msg_bytes, bytes):
            self._uid_counter += 1
            uid = str(self._uid_counter)
            self._ensure_folder(folder)[uid] = msg_bytes
            return ("OK", [b"APPEND completed"])
        return ("NO", [b"BAD append"])

    def uid(self, command: str, *args: object) -> tuple[str, list]:
        folder = self._ensure_folder(self._selected)
        cmd = command.upper()

        if cmd == "SEARCH":
            criteria = " ".join(str(a) for a in args)
            if "UNSEEN" in criteria:
                return ("OK", [b""])
            if "FROM" in criteria:
                addr = criteria.split('"')[1] if '"' in criteria else ""
                matched = [
                    uid
                    for uid, msg in folder.items()
                    if addr.encode() in msg
                ]
                uids = b" ".join(u.encode() for u in matched)
                return ("OK", [uids or b""])
            uids = b" ".join(k.encode() for k in folder)
            return ("OK", [uids or b""])

        if cmd == "FETCH":
            uid = str(args[0])
            specifier = str(args[1])
            msg_bytes = folder.get(uid, b"")
            if not msg_bytes:
                return ("NO", [b"UID not found"])
            if "RFC822" in specifier:
                return ("OK", [(b"1 (RFC822 {%d}" % len(msg_bytes), msg_bytes)])
            elif "HEADER" in specifier:
                return ("OK", [(b"1 (BODY[HEADER] {%d}" % len(msg_bytes), msg_bytes)])
            return ("OK", [b""])

        return ("NO", [b"Unknown command"])

    def expunge(self) -> tuple[str, list]:
        return ("OK", [b"EXPUNGE completed"])


def _build_mock_imap(fake: FakeIMAP) -> MagicMock:
    instance = MagicMock()
    instance.select = fake.select
    instance.close = fake.close
    instance.logout = fake.logout
    instance.login = fake.login
    instance.append = fake.append
    instance.uid = fake.uid
    instance.expunge = fake.expunge
    mock_cls = MagicMock()
    mock_cls.return_value = instance
    return mock_cls


class TestEmailSearchAndRead:
    """End-to-end composite tool with mocked IMAP."""

    @pytest.mark.anyio
    async def test_search_and_read_composite(self, config: EmailConfig) -> None:
        fake = FakeIMAP()
        fake._ensure_folder("INBOX")["1"] = (
            b"From: alice@example.com\r\n"
            b"Subject: Hello World\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"\r\nThis is the body."
        )
        fake._ensure_folder("INBOX")["2"] = (
            b"From: bob@example.com\r\n"
            b"Subject: Another\r\n"
            b"Date: Tue, 02 Jan 2024 00:00:00 +0000\r\n"
            b"\r\nAnother body."
        )
        mock_imap_cls = _build_mock_imap(fake)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls):
            adapter = EmailAdapter(config)
            tool = make_email_search_and_read_tool(adapter)
            assert tool is not None

            result = await tool(query="FROM:alice", limit=5)
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["uid"] == "1"
            assert result[0]["from"] == "alice@example.com"
            assert result[0]["subject"] == "Hello World"
            assert result[0]["body"] == "This is the body."
            assert result[0]["snippet"] == "This is the body."

    @pytest.mark.anyio
    async def test_returns_empty_list_when_no_matches(self, config: EmailConfig) -> None:
        fake = FakeIMAP()
        mock_imap_cls = _build_mock_imap(fake)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls):
            adapter = EmailAdapter(config)
            tool = make_email_search_and_read_tool(adapter)
            assert tool is not None

            result = await tool(query="FROM:nobody", limit=5)
            assert result == []

    def test_factory_returns_none_when_unconfigured(self) -> None:
        adapter = EmailAdapter(EmailConfig(imap_host=""))
        assert make_email_search_and_read_tool(adapter) is None
