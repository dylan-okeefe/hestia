"""Basic end-to-end tests through Matrix.

These tests exercise the full stack: platform adapter → orchestrator →
inference → tools → response.

Prerequisites:
    - Docker and docker-compose
    - Synapse running on localhost:8008
    - Hestia bot configured and connected to the test server
    - Mock llama server for deterministic responses (optional)

Run with:
    docker-compose -f tests/e2e/docker-compose.yml up -d
    HESTIA_TEST_SYNAPSE_URL=http://localhost:8008 pytest tests/e2e/ -v
    docker-compose -f tests/e2e/docker-compose.yml down
"""

from __future__ import annotations

import re

import pytest

# All e2e tests require Synapse to be running
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(reason="E2E tests require Docker - run manually with docker-compose"),
]


class TestBasicRoundtrip:
    """Test basic message round-trip through Matrix."""

    async def test_hello_gets_response(self, require_synapse, matrix_test_client):
        """Send 'hello' → get a text response (basic round-trip)."""
        # This test is skipped by default - see pytestmark above
        client = matrix_test_client

        # Ensure we have a room
        if client.room_id is None:
            await client.create_room("Test Hello")

        response = await client.send_and_wait("hello", timeout=10.0)

        assert response
        assert len(response) > 0
        # Response should contain a greeting
        assert any(
            word in response.lower() for word in ["hello", "hi", "greetings", "hestia"]
        )

    async def test_time_query_triggers_tool(self, require_synapse, matrix_test_client):
        """Send 'what time is it?' → response contains a time string (tool use)."""
        client = matrix_test_client

        if client.room_id is None:
            await client.create_room("Test Time")

        response = await client.send_and_wait("what time is it?", timeout=15.0)

        # Should contain a time-like pattern (HH:MM or similar)
        time_pattern = r"\d{1,2}:\d{2}"
        assert re.search(time_pattern, response), f"Expected time in response: {response}"


class TestMemoryRoundtrip:
    """Test memory persistence through e2e flow."""

    async def test_memory_save_and_retrieve(self, require_synapse, matrix_test_client):
        """Save memory, then search for it → response contains saved data."""
        client = matrix_test_client

        if client.room_id is None:
            await client.create_room("Test Memory")

        # Save memory
        save_response = await client.send_and_wait(
            "remember that my favorite color is blue",
            timeout=15.0,
        )
        assert save_response  # Should get acknowledgment

        # Search for memory
        search_response = await client.send_and_wait(
            "search for my favorite color",
            timeout=15.0,
        )

        # Response should mention blue
        assert "blue" in search_response.lower()


class TestMultiTurnConversation:
    """Test context persistence across multiple turns."""

    async def test_context_persists_across_turns(self, require_synapse, matrix_test_client):
        """Second message references first → context persistence works."""
        client = matrix_test_client

        if client.room_id is None:
            await client.create_room("Test Context")

        # First message
        response1 = await client.send_and_wait("my name is TestUser", timeout=10.0)
        assert response1

        # Second message referencing first
        response2 = await client.send_and_wait("what is my name?", timeout=10.0)

        # Should reference the name from the first message
        assert "testuser" in response2.lower() or "test user" in response2.lower()


class TestToolConfirmation:
    """Test tool confirmation behavior in Matrix mode."""

    async def test_write_file_requires_confirmation(self, require_synapse, matrix_test_client):
        """Send a request that triggers write_file → tool is denied without confirmation."""
        client = matrix_test_client

        if client.room_id is None:
            await client.create_room("Test Confirmation")

        response = await client.send_and_wait(
            "write a file called test.txt with content hello",
            timeout=15.0,
        )

        # Without a confirm callback, the tool should be denied
        # Response should explain why the tool couldn't be used
        assert response
        denial_indicators = [
            "cannot",
            "unable",
            "denied",
            "confirmation",
            "not allowed",
            "refused",
        ]
        assert any(
            indicator in response.lower() for indicator in denial_indicators
        ), f"Expected denial message, got: {response}"


class TestMockLlamaIntegration:
    """Tests using mock llama server for deterministic responses."""

    @pytest.mark.skip(reason="Requires mock llama server to be running")
    async def test_mock_server_canned_response(self, require_synapse, matrix_test_client):
        """Test with mock server returning deterministic responses."""
        # This test would be used when running with the mock llama server
        # for completely deterministic, fast e2e tests
        client = matrix_test_client

        if client.room_id is None:
            await client.create_room("Test Mock")

        response = await client.send_and_wait("hello", timeout=5.0)

        # With mock server, we should get the exact canned response
        assert "Hello! I'm Hestia" in response
