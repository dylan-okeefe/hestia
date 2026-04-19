"""Integration test for email draft → list → send roundtrip.

Mocks ``imaplib.IMAP4_SSL`` and ``smtplib.SMTP`` so no real mail server is
required.  Verifies that the adapter issues the correct IMAP/SMTP commands
and that the draft is moved to Sent after a successful send.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hestia.config import EmailConfig
from hestia.email.adapter import EmailAdapter
from hestia.tools.builtin.email_tools import make_email_tools


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
        # args are typically (flags, date_time, message_bytes)
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
            # Return all UIDs for simplicity
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

        if cmd == "COPY":
            uid = str(args[0])
            target = str(args[1])
            msg_bytes = folder.get(uid, b"")
            if msg_bytes:
                self._uid_counter += 1
                self._ensure_folder(target)[str(self._uid_counter)] = msg_bytes
                return ("OK", [b"COPY completed"])
            return ("NO", [b"UID not found"])

        if cmd == "STORE":
            uid = str(args[0])
            if uid in folder:
                return ("OK", [b"STORE completed"])
            return ("NO", [b"UID not found"])

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


class TestEmailRoundtrip:
    """End-to-end email workflow with mocked IMAP/SMTP."""

    @pytest.mark.anyio
    async def test_draft_list_read_send(self, config: EmailConfig) -> None:
        fake = FakeIMAP()
        mock_imap_cls = _build_mock_imap(fake)
        mock_smtp = MagicMock()

        with (
            patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls),
            patch("hestia.email.adapter.smtplib.SMTP", mock_smtp),
        ):
            adapter = EmailAdapter(config)

            # 1. Create a draft
            draft_id = await adapter.create_draft(
                to="recipient@example.com",
                subject="Test draft",
                body="This is a test draft.",
            )
            assert draft_id != "draft-unknown"

            # 2. List drafts
            drafts = await adapter.list_messages(folder="Drafts", limit=10)
            assert len(drafts) == 1
            assert drafts[0]["subject"] == "Test draft"

            # 3. Verify the draft exists in the fake IMAP store
            assert "Drafts" in fake._folders
            assert draft_id in fake._folders["Drafts"]

            # 4. Send the draft
            send_result = await adapter.send_draft(draft_id)
            assert "Sent" in send_result

            # 5. Verify SMTP send_message was called
            mock_smtp.return_value.send_message.assert_called_once()
            sent_msg = mock_smtp.return_value.send_message.call_args[0][0]
            assert sent_msg["To"] == "recipient@example.com"
            assert sent_msg["Subject"] == "Test draft"

            # 6. Verify draft was copied to Sent
            assert "Sent" in fake._folders
            sent_uids = list(fake._folders["Sent"].keys())
            assert len(sent_uids) == 1

            # 7. Verify draft was copied to Sent (already checked above)
            assert len(fake._folders.get("Sent", {})) == 1

    @pytest.mark.anyio
    async def test_search_and_flag(self, config: EmailConfig) -> None:
        fake = FakeIMAP()
        # Seed INBOX with a message
        fake._ensure_folder("INBOX")["1"] = (
            b"From: alice@example.com\r\n"
            b"Subject: Hello\r\n"
            b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            b"\r\nBody text."
        )
        mock_imap_cls = _build_mock_imap(fake)

        with patch("hestia.email.adapter.imaplib.IMAP4_SSL", mock_imap_cls):
            adapter = EmailAdapter(config)

            uids = await adapter.search_messages("FROM:alice@example.com")
            assert "1" in uids

            flag_result = await adapter.flag_message("1", "read")
            assert "\\Seen" in flag_result

            move_result = await adapter.move_message("1", "Archive")
            assert "Archive" in move_result


class TestEmailToolsFactory:
    """Verify the tool factory registers tools correctly."""

    def test_returns_empty_list_when_unconfigured(self) -> None:
        tools = make_email_tools(EmailConfig(imap_host=""))
        assert tools == []

    def test_returns_all_tools_when_configured(self) -> None:
        tools = make_email_tools(EmailConfig(imap_host="imap.test"))
        names = [t.__hestia_tool__.name for t in tools]  # type: ignore[attr-defined]
        assert "email_list" in names
        assert "email_read" in names
        assert "email_search" in names
        assert "email_draft" in names
        assert "email_send" in names
        assert "email_move" in names
        assert "email_flag" in names

    def test_email_send_requires_confirmation(self) -> None:
        tools = make_email_tools(EmailConfig(imap_host="imap.test"))
        send_tool = next(t for t in tools if t.__hestia_tool__.name == "email_send")  # type: ignore[attr-defined]
        assert send_tool.__hestia_tool__.requires_confirmation  # type: ignore[attr-defined]

    def test_email_send_has_email_send_capability(self) -> None:
        from hestia.tools.capabilities import EMAIL_SEND

        tools = make_email_tools(EmailConfig(imap_host="imap.test"))
        send_tool = next(t for t in tools if t.__hestia_tool__.name == "email_send")  # type: ignore[attr-defined]
        assert EMAIL_SEND in send_tool.__hestia_tool__.capabilities  # type: ignore[attr-defined]
