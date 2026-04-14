"""Unit tests for MatrixAdapter."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.config import MatrixConfig
from hestia.errors import PlatformError
from hestia.platforms.matrix_adapter import MatrixAdapter


class TestMatrixAdapter:
    def test_name_is_matrix(self):
        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)
        assert adapter.name == "matrix"

    def test_requires_access_token(self):
        cfg = MatrixConfig(access_token="", user_id="@bot:matrix.org")
        with pytest.raises(ValueError, match="access_token is required"):
            MatrixAdapter(cfg)

    def test_requires_user_id(self):
        cfg = MatrixConfig(access_token="test_token", user_id="")
        with pytest.raises(ValueError, match="user_id is required"):
            MatrixAdapter(cfg)

    def test_allowed_rooms_empty_denies_all(self):
        """Empty allowed_rooms is secure default: deny all inbound."""
        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)
        assert adapter._is_allowed("!room:matrix.org") is False

    def test_allowed_rooms_by_room_id(self):
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!allowed:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)
        assert adapter._is_allowed("!allowed:matrix.org") is True
        assert adapter._is_allowed("!other:matrix.org") is False

    def test_allowed_rooms_by_alias(self):
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["#test-room:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)
        assert adapter._is_allowed("#test-room:matrix.org") is True
        assert adapter._is_allowed("!room:matrix.org") is False

    def test_send_message_raises_when_not_started(self):
        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(adapter.send_message("!room:matrix.org", "test"))

    def test_edit_message_raises_when_not_started(self):
        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(adapter.edit_message("!room:matrix.org", "$event123", "test"))

    @pytest.mark.asyncio
    async def test_send_error_prefixes_with_error_emoji(self):
        """send_error should prefix the message with an error indicator."""
        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)

        # Mock send_message
        with patch.object(adapter, "send_message", new_callable=AsyncMock) as mock_send:
            await adapter.send_error("!room:matrix.org", "Something went wrong")

            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert call_args[0] == "!room:matrix.org"
            assert "Error:" in call_args[1]
            assert "Something went wrong" in call_args[1]

    @pytest.mark.asyncio
    async def test_rate_limiting_tracks_last_edit_time(self):
        """edit_message should track last edit time for rate limiting."""
        from nio import RoomSendResponse

        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            rate_limit_edits_seconds=1.5,
        )
        adapter = MatrixAdapter(cfg)

        # Mock the client with proper RoomSendResponse
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(event_id="$new_event", room_id="!room:matrix.org")
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        # First edit
        await adapter.edit_message("!room:matrix.org", "$event1", "edit1")
        assert "$event1" in adapter._last_edit_times
        first_edit_time = adapter._last_edit_times["$event1"]

        # Second edit should update the time
        await adapter.edit_message("!room:matrix.org", "$event1", "edit2")
        second_edit_time = adapter._last_edit_times["$event1"]
        assert second_edit_time >= first_edit_time

    def test_constructor_sets_config(self):
        cfg = MatrixConfig(
            access_token="my_token",
            user_id="@hestia:matrix.org",
            homeserver="https://custom.matrix.org",
            device_id="custom_device",
            allowed_rooms=["!room1:matrix.org", "!room2:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)

        assert adapter._config.access_token == "my_token"
        assert adapter._config.user_id == "@hestia:matrix.org"
        assert adapter._config.homeserver == "https://custom.matrix.org"
        assert adapter._config.device_id == "custom_device"
        assert adapter._config.allowed_rooms == ["!room1:matrix.org", "!room2:matrix.org"]

    @pytest.mark.asyncio
    async def test_handle_room_message_ignores_own_messages(self):
        """Bot should not respond to its own messages."""
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)

        # Mock callback
        callback = AsyncMock()
        adapter._on_message = callback

        # Create mock room and event
        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        mock_event = MagicMock()
        mock_event.sender = "@bot:matrix.org"  # Same as bot
        mock_event.body = "Hello"

        await adapter._handle_room_message(mock_room, mock_event)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_room_message_ignores_non_allowed_rooms(self):
        """Bot should not respond to messages from non-allowed rooms."""
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!allowed:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)

        callback = AsyncMock()
        adapter._on_message = callback

        mock_room = MagicMock()
        mock_room.room_id = "!notallowed:matrix.org"

        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "Hello"

        await adapter._handle_room_message(mock_room, mock_event)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_room_message_calls_callback_for_valid_message(self):
        """Bot should call on_message for valid messages from allowed rooms."""
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)

        callback = AsyncMock()
        adapter._on_message = callback

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "Hello bot"

        await adapter._handle_room_message(mock_room, mock_event)

        callback.assert_called_once_with("matrix", "!room:matrix.org", "Hello bot")

    @pytest.mark.asyncio
    async def test_handle_room_message_strips_whitespace(self):
        """Bot should strip whitespace from message bodies."""
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)

        callback = AsyncMock()
        adapter._on_message = callback

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = "   Hello with whitespace   "

        await adapter._handle_room_message(mock_room, mock_event)

        callback.assert_called_once_with("matrix", "!room:matrix.org", "Hello with whitespace")

    @pytest.mark.asyncio
    async def test_handle_room_message_ignores_empty_messages(self):
        """Bot should ignore empty or whitespace-only messages."""
        cfg = MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
        adapter = MatrixAdapter(cfg)

        callback = AsyncMock()
        adapter._on_message = callback

        mock_room = MagicMock()
        mock_room.room_id = "!room:matrix.org"

        # Empty message
        mock_event = MagicMock()
        mock_event.sender = "@user:matrix.org"
        mock_event.body = ""

        await adapter._handle_room_message(mock_room, mock_event)
        callback.assert_not_called()

        # Whitespace-only message
        mock_event.body = "   "
        await adapter._handle_room_message(mock_room, mock_event)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_closes_client(self):
        """stop() should close the Matrix client."""
        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)

        adapter._sync_task = None
        adapter._stop_event = MagicMock()
        mock_client = AsyncMock()
        adapter._client = mock_client

        await adapter.stop()

        mock_client.close.assert_called_once()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_send_message_returns_event_id(self):
        """send_message should return the event ID from the response."""
        from nio import RoomSendResponse

        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)

        # Mock the client with real RoomSendResponse
        mock_client = AsyncMock()
        mock_response = RoomSendResponse(event_id="$event123456", room_id="!room:matrix.org")
        mock_client.room_send.return_value = mock_response
        adapter._client = mock_client

        result = await adapter.send_message("!room:matrix.org", "Hello")

        assert result == "$event123456"
        mock_client.room_send.assert_called_once()

    def test_send_message_raises_on_error_response(self):
        """send_message should raise PlatformError on error response."""
        from nio import RoomSendError

        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)

        async def test_raises():
            mock_client = AsyncMock()
            mock_client.room_send.return_value = RoomSendError(message="Test error")
            adapter._client = mock_client

            await adapter.send_message("!room:matrix.org", "Hello")

        with pytest.raises(PlatformError):
            asyncio.run(test_raises())

    def test_edit_message_raises_on_error_response(self):
        """edit_message should raise PlatformError on error response."""
        from nio import RoomSendError

        cfg = MatrixConfig(access_token="test_token", user_id="@bot:matrix.org")
        adapter = MatrixAdapter(cfg)

        async def test_raises():
            mock_client = AsyncMock()
            mock_client.room_send.return_value = RoomSendError(message="Test error")
            adapter._client = mock_client

            await adapter.edit_message("!room:matrix.org", "$event123", "Hello")

        with pytest.raises(PlatformError):
            asyncio.run(test_raises())
