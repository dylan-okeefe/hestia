"""Pytest fixtures and test client for Matrix e2e tests.

These tests require a running Synapse server. When unavailable,
tests are skipped so default pytest runs stay green.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

import pytest

# Skip entire module if matrix-nio not available or Docker unavailable
pytest.importorskip("nio", reason="matrix-nio not installed")

from nio import AsyncClient, RoomSendResponse

# Configuration from environment
SYNAPSE_URL = os.environ.get("HESTIA_TEST_SYNAPSE_URL", "http://localhost:8008")
TEST_USER = os.environ.get("HESTIA_TEST_USER", "@testuser:localhost")
TEST_PASSWORD = os.environ.get("HESTIA_TEST_PASSWORD", "testpass123")
HESTIA_USER = os.environ.get("HESTIA_TEST_HESTIA_USER", "@hestia:localhost")


def is_synapse_available() -> bool:
    """Check if Synapse server is available."""
    import urllib.request

    try:
        urllib.request.urlopen(SYNAPSE_URL, timeout=2)
        return True
    except Exception:
        return False


class HestiaMatrixTestClient:
    """Test client that talks to Hestia through Matrix.

    Usage:
        client = HestiaMatrixTestClient(synapse_url, room_id)
        await client.login()
        response = await client.send_and_wait("Hello Hestia!")
    """

    def __init__(self, homeserver_url: str, room_id: str | None = None):
        self.homeserver_url = homeserver_url
        self.room_id = room_id
        self._client: AsyncClient | None = None
        self._access_token: str | None = None
        self._responses: list[tuple[str, str]] = []  # (sender, content)

    async def login(self, username: str, password: str) -> None:
        """Login to the Matrix homeserver."""
        # Extract localpart from username (@user:server -> user)
        localpart = username.split(":")[0].lstrip("@")

        self._client = AsyncClient(self.homeserver_url, username)
        response = await self._client.login(password)

        if hasattr(response, "access_token"):
            self._access_token = response.access_token
            self._client.access_token = self._access_token
        else:
            raise RuntimeError(f"Login failed: {response}")

    async def create_room(self, name: str = "Hestia Test Room") -> str:
        """Create a new room and return the room ID."""
        if self._client is None:
            raise RuntimeError("Not logged in")

        from nio import RoomCreateResponse

        response = await self._client.room_create(name=name)
        if isinstance(response, RoomCreateResponse):
            self.room_id = response.room_id
            return response.room_id
        raise RuntimeError(f"Room creation failed: {response}")

    async def invite_user(self, user_id: str) -> None:
        """Invite a user to the test room."""
        if self._client is None or self.room_id is None:
            raise RuntimeError("Not logged in or no room")

        await self._client.room_invite(self.room_id, user_id)

    async def join_room(self, room_id: str) -> None:
        """Join a room."""
        if self._client is None:
            raise RuntimeError("Not logged in")

        await self._client.join(room_id)
        self.room_id = room_id

    async def send_and_wait(
        self,
        message: str,
        timeout: float = 30.0,
        wait_for_sender: str | None = None,
    ) -> str:
        """Send a message and wait for Hestia's response.

        Args:
            message: The message to send
            timeout: Maximum time to wait for response
            wait_for_sender: Wait for specific sender (default: HESTIA_USER)

        Returns:
            The response text from Hestia
        """
        if self._client is None or self.room_id is None:
            raise RuntimeError("Not logged in or no room")

        target_sender = wait_for_sender or HESTIA_USER

        # Send the message
        content = {"msgtype": "m.text", "body": message}
        send_response = await self._client.room_send(
            room_id=self.room_id,
            message_type="m.room.message",
            content=content,
        )

        if not isinstance(send_response, RoomSendResponse):
            raise RuntimeError(f"Failed to send message: {send_response}")

        # Wait for response with timeout
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            # Sync to get new messages
            sync_response = await self._client.sync(timeout=1000)
            if hasattr(sync_response, "rooms"):
                room_info = sync_response.rooms.join.get(self.room_id)
                if room_info:
                    for event in room_info.timeline.events:
                        if (
                            hasattr(event, "sender")
                            and hasattr(event, "body")
                            and event.sender == target_sender
                        ):
                            return event.body

            await asyncio.sleep(0.5)

        raise TimeoutError(f"No response from {target_sender} within {timeout}s")

    async def send_and_collect(
        self,
        message: str,
        count: int = 1,
        timeout: float = 30.0,
        wait_for_sender: str | None = None,
    ) -> list[str]:
        """Send a message and collect N responses.

        Args:
            message: The message to send
            count: Number of responses to collect
            timeout: Maximum time to wait for all responses
            wait_for_sender: Wait for specific sender (default: HESTIA_USER)

        Returns:
            List of response texts
        """
        if self._client is None or self.room_id is None:
            raise RuntimeError("Not logged in or no room")

        target_sender = wait_for_sender or HESTIA_USER
        responses: list[str] = []

        # Send the message
        content = {"msgtype": "m.text", "body": message}
        await self._client.room_send(
            room_id=self.room_id,
            message_type="m.room.message",
            content=content,
        )

        # Collect responses with timeout
        start_time = time.monotonic()
        while len(responses) < count and time.monotonic() - start_time < timeout:
            sync_response = await self._client.sync(timeout=1000)
            if hasattr(sync_response, "rooms"):
                room_info = sync_response.rooms.join.get(self.room_id)
                if room_info:
                    for event in room_info.timeline.events:
                        if (
                            hasattr(event, "sender")
                            and hasattr(event, "body")
                            and event.sender == target_sender
                        ):
                            responses.append(event.body)
                            if len(responses) >= count:
                                return responses

            await asyncio.sleep(0.5)

        if len(responses) < count:
            raise TimeoutError(
                f"Only received {len(responses)}/{count} responses within {timeout}s"
            )

        return responses

    async def close(self) -> None:
        """Close the client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None


@pytest.fixture
async def matrix_test_client() -> HestiaMatrixTestClient:
    """Fixture providing a logged-in Matrix test client."""
    pytest.skip("Matrix e2e tests require Docker - run manually with docker-compose")
    # This code is unreachable but shows the intended implementation:
    # client = HestiaMatrixTestClient(SYNAPSE_URL)
    # await client.login(TEST_USER, TEST_PASSWORD)
    # yield client
    # await client.close()


@pytest.fixture(scope="session")
def synapse_available() -> bool:
    """Check if Synapse is available for testing."""
    return is_synapse_available()


@pytest.fixture
def require_synapse(synapse_available: bool) -> None:
    """Skip test if Synapse is not available."""
    if not synapse_available:
        pytest.skip("Synapse server not available - run 'docker-compose up -d' in tests/e2e/")
