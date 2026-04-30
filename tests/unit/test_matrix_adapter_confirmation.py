"""Unit tests for MatrixAdapter confirmation flow."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from nio import RoomSendResponse

from hestia.config import MatrixConfig
from hestia.platforms.matrix_adapter import MatrixAdapter


class TestMatrixConfirmation:
    """Tests for the reply-pattern confirmation flow."""

    @pytest.fixture
    def adapter(self):
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        return MatrixAdapter(cfg)

    @pytest.mark.asyncio
    async def test_request_confirmation_posts_prompt(self, adapter):
        """Verify the confirmation message is posted to the room."""
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(event_id="$event123", room_id="!room:matrix.org")
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "!room:matrix.org", "write_file", {"path": "test.txt"}
            )
        )
        await asyncio.sleep(0.05)

        assert mock_client.room_send.call_count == 1
        call_kwargs = mock_client.room_send.call_args[1]
        content = call_kwargs["content"]
        assert "write_file" in content["body"]
        assert "Reply 'yes' or 'no'" in content["body"]

        # Simulate 'yes' reply
        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "yes"
        mock_event.source = {
            "content": {
                "m.relates_to": {
                    "m.in_reply_to": {"event_id": "$event123"}
                }
            }
        }

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        adapter._on_message = AsyncMock()
        await adapter._handle_room_message(mock_room, mock_event)

        result = await confirm_task
        assert result is True

    @pytest.mark.asyncio
    async def test_request_confirmation_denied_by_no(self, adapter):
        """Verify 'no' reply returns False."""
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(event_id="$event456", room_id="!room:matrix.org")
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "!room:matrix.org", "terminal", {"command": "ls"}
            )
        )
        await asyncio.sleep(0.05)

        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "no"
        mock_event.source = {
            "content": {
                "m.relates_to": {
                    "m.in_reply_to": {"event_id": "$event456"}
                }
            }
        }

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        adapter._on_message = AsyncMock()
        await adapter._handle_room_message(mock_room, mock_event)

        result = await confirm_task
        assert result is False

    @pytest.mark.asyncio
    async def test_request_confirmation_times_out(self, adapter):
        """Verify timeout returns False."""
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(event_id="$event789", room_id="!room:matrix.org")
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client
        adapter._confirmation_timeout_seconds = 0.05

        result = await adapter.request_confirmation(
            "!room:matrix.org", "write_file", {"path": "test.txt"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_confirmation_reply_not_routed_to_orchestrator(self, adapter):
        """Verify a confirmation reply is consumed and not passed to on_message."""
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(event_id="$event999", room_id="!room:matrix.org")
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        confirm_task = asyncio.create_task(
            adapter.request_confirmation(
                "!room:matrix.org", "terminal", {"command": "ls"}
            )
        )
        await asyncio.sleep(0.05)

        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "yes"
        mock_event.source = {
            "content": {
                "m.relates_to": {
                    "m.in_reply_to": {"event_id": "$event999"}
                }
            }
        }

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        on_message_mock = AsyncMock()
        adapter._on_message = on_message_mock
        await adapter._handle_room_message(mock_room, mock_event)

        on_message_mock.assert_not_called()
        assert await confirm_task is True

    @pytest.mark.asyncio
    async def test_non_reply_message_routed_normally(self, adapter):
        """Verify regular messages still reach on_message."""
        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "Hello bot"
        mock_event.source = {"content": {}}

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        on_message_mock = AsyncMock()
        adapter._on_message = on_message_mock
        await adapter._handle_room_message(mock_room, mock_event)

        on_message_mock.assert_called_once_with("matrix", "!room:matrix.org", "Hello bot")

    @pytest.mark.asyncio
    async def test_request_confirmation_raises_when_not_started(self, adapter):
        with pytest.raises(RuntimeError, match="not started"):
            await adapter.request_confirmation("!room:matrix.org", "terminal", {})

    def test_extract_in_reply_to_with_valid_reply(self, adapter):
        event = MagicMock()
        event.source = {
            "content": {
                "m.relates_to": {
                    "m.in_reply_to": {"event_id": "$original"}
                }
            }
        }
        assert adapter._extract_in_reply_to(event) == "$original"  # type: ignore[arg-type]

    def test_extract_in_reply_to_without_reply(self, adapter):
        event = MagicMock()
        event.source = {"content": {}}
        assert adapter._extract_in_reply_to(event) is None  # type: ignore[arg-type]

    def test_extract_in_reply_to_with_malformed_source(self, adapter):
        event = MagicMock()
        event.source = {"content": "not a dict"}
        assert adapter._extract_in_reply_to(event) is None  # type: ignore[arg-type]
