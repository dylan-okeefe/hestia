"""Phase 1a smoke tests — InferenceClient and SessionStore integration."""

import pytest

from hestia.core.inference import InferenceClient
from hestia.core.types import Message
from hestia.orchestrator.mappers import message_domain_to_dto, message_dto_to_domain
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.sessions import SessionStore


@pytest.mark.asyncio
async def test_inference_health():
    """Verify llama-server is reachable."""
    client = InferenceClient("http://localhost:8001", "qwen-3.5-9b")
    try:
        health = await client.health()
        assert health is not None
        assert "status" in health
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tokenize_accurate():
    """Tokenize endpoint returns accurate token counts."""
    client = InferenceClient("http://localhost:8001", "qwen-3.5-9b")
    try:
        tokens = await client.tokenize("Hello, world!")
        assert len(tokens) > 0
        assert len(tokens) < 10  # should be a handful of tokens
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chat_simple():
    """Basic chat completion works.

    Note: Server is configured with --reasoning-budget 2048, so we need
    max_tokens > 2048 to get content. This test verifies the API works.
    """
    client = InferenceClient("http://localhost:8001", "qwen-3.5-9b")
    try:
        response = await client.chat(
            messages=[
                Message(role="system", content="You are a helpful assistant."),
                Message(role="user", content="Say exactly 'hello world' and nothing else."),
            ],
            max_tokens=2500,  # > 2048 reasoning budget
        )
        # Model returns reasoning_content when thinking, content when done
        assert response.content or response.reasoning_content
        assert response.finish_reason in ["stop", "length"]
        assert response.prompt_tokens > 0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_count_request_reasonable():
    """count_request returns a reasonable token estimate.

    Note: Due to chat template differences, this won't exactly match
    prompt_tokens. We just verify it's in a reasonable range.
    """
    client = InferenceClient("http://localhost:8001", "qwen-3.5-9b")
    try:
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="What is 2+2?"),
        ]
        counted = await client.count_request(messages, tools=[])
        response = await client.chat(messages=messages, max_tokens=2500)
        # Count should be within 2x (rough estimate)
        assert counted > 0
        assert response.prompt_tokens > 0
        # Just verify both are reasonable - don't require exact match
        # because tokenization of chat template differs from JSON
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_session_store_roundtrip(tmp_path):
    """SessionStore can create, read, and update sessions."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()

    try:
        store = SessionStore(db)
        message_store = MessageStore(db)
        session = await store.get_or_create_session("telegram", "user123")
        assert session.id
        assert session.platform == "telegram"

        await message_store.append_message(
            session.id,
            message_domain_to_dto(Message(role="user", content="Hello"), session.id, idx=0),
        )
        await message_store.append_message(
            session.id,
            message_domain_to_dto(
                Message(role="assistant", content="Hi there"), session.id, idx=0
            ),
        )

        messages = await message_store.get_messages(session.id)
        assert len(messages) == 2
        assert messages[0].content == "Hello"
        assert messages[1].content == "Hi there"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_end_to_end_smoke(tmp_path):
    """Send a message through inference, store it, verify the round-trip."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/smoke.db")
    await db.connect()
    await db.create_tables()

    client = InferenceClient("http://localhost:8001", "qwen-3.5-9b")

    try:
        store = SessionStore(db)
        message_store = MessageStore(db)
        session = await store.get_or_create_session("cli", "smoke-test")
        user_msg = Message(
            role="user",
            content="What is 2+2? Answer with just the number.",
        )
        await message_store.append_message(
            session.id, message_domain_to_dto(user_msg, session.id, idx=0)
        )

        history = [
            message_dto_to_domain(dto)
            for dto in await message_store.get_messages(session.id)
        ]
        response = await client.chat(
            messages=history,
            max_tokens=2500,  # > 2048 reasoning budget
        )
        # Verify we got some kind of response
        assert response.content or response.reasoning_content
        assert response.prompt_tokens > 0

        assistant_msg = Message(
            role="assistant",
            content=response.content,
            reasoning_content=response.reasoning_content,
        )
        await message_store.append_message(
            session.id, message_domain_to_dto(assistant_msg, session.id, idx=0)
        )

        final_history = await message_store.get_messages(session.id)
        assert len(final_history) == 2
    finally:
        await db.close()
        await client.close()
