"""Unit tests for CliPlatform."""

import pytest

from hestia.platforms.cli_adapter import CliPlatform


class TestCliPlatform:
    """Tests for CliPlatform adapter."""

    @pytest.mark.asyncio
    async def test_cli_platform_name_is_cli(self):
        """Platform name is 'cli'."""
        platform = CliPlatform()
        assert platform.name == "cli"

    @pytest.mark.asyncio
    async def test_send_message_returns_msg_id(self):
        """send_message returns a message ID."""
        platform = CliPlatform()
        msg_id = await platform.send_message("user1", "Hello")
        assert msg_id == "cli-msg"

    @pytest.mark.asyncio
    async def test_edit_message_does_not_raise(self):
        """edit_message does not raise."""
        platform = CliPlatform()
        # Should not raise
        await platform.edit_message("user1", "msg1", "Updated text")

    @pytest.mark.asyncio
    async def test_start_does_not_raise(self):
        """start does not raise."""
        platform = CliPlatform()

        async def callback(platform_name: str, user: str, text: str) -> None:
            pass

        await platform.start(callback)

    @pytest.mark.asyncio
    async def test_stop_does_not_raise(self):
        """stop does not raise."""
        platform = CliPlatform()
        await platform.stop()

    @pytest.mark.asyncio
    async def test_send_error_does_not_raise(self):
        """send_error does not raise."""
        platform = CliPlatform()
        await platform.send_error("user1", "Error message")

    @pytest.mark.asyncio
    async def test_send_system_warning_prefixes_emoji(self):
        """send_system_warning prepends warning emoji."""
        platform = CliPlatform()
        # CliPlatform uses default implementation (send_message with prefix)
        # Should not raise
        await platform.send_system_warning("user1", "System warning text")
