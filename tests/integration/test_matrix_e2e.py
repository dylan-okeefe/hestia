# mypy: disable-error-code="no-untyped-def,import-not-found,import-untyped,no-any-return"
"""Matrix E2E tests against a real homeserver (skipped without env).

Required environment variables:
    HESTIA_MATRIX_HOMESERVER      - Bot homeserver URL
    HESTIA_MATRIX_USER_ID         - Bot MXID
    HESTIA_MATRIX_ACCESS_TOKEN    - Bot access token
    HESTIA_MATRIX_TESTER_USER_ID  - Tester MXID
    HESTIA_MATRIX_TESTER_ACCESS_TOKEN - Tester access token
    HESTIA_MATRIX_TEST_ROOM_ID    - Room ID both users share

Optional:
    HESTIA_MATRIX_DEVICE_ID       - Bot device ID (default: hestia-bot)
    HESTIA_MATRIX_TESTER_DEVICE_ID - Tester device ID (default: hestia-e2e-tester)
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

pytest.importorskip("nio", reason="matrix-nio not installed")

from helpers import FakeInferenceClient, FakePolicyEngine
from nio import AsyncClient, RoomMessageText, RoomSendResponse, SyncResponse

from hestia.artifacts.store import ArtifactStore
from hestia.config import MatrixConfig
from hestia.context.builder import ContextBuilder
from hestia.core.types import ChatResponse, Message, ToolCall
from hestia.memory.store import MemoryStore
from hestia.orchestrator import Orchestrator
from hestia.persistence.db import Database
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.sessions import SessionStore
from hestia.persistence.trace_store import TraceStore
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.tools.builtin import current_time, http_get, terminal
from hestia.tools.builtin.list_dir import make_list_dir_tool
from hestia.tools.builtin.memory_tools import (
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
)
from hestia.tools.builtin.read_artifact import make_read_artifact_tool
from hestia.tools.builtin.read_file import make_read_file_tool
from hestia.tools.builtin.write_file import make_write_file_tool
from hestia.tools.registry import ToolRegistry

E2E_MEMORY_TAG = "e2e_hestia_l12"


def _env_or_none(name: str) -> str | None:
    val = os.environ.get(name, "").strip()
    return val if val else None


def _skip_if_env_missing() -> None:
    required = [
        "HESTIA_MATRIX_HOMESERVER",
        "HESTIA_MATRIX_USER_ID",
        "HESTIA_MATRIX_ACCESS_TOKEN",
        "HESTIA_MATRIX_TESTER_USER_ID",
        "HESTIA_MATRIX_TESTER_ACCESS_TOKEN",
        "HESTIA_MATRIX_TEST_ROOM_ID",
    ]
    missing = [name for name in required if _env_or_none(name) is None]
    if missing:
        pytest.skip(f"Matrix E2E env vars missing: {', '.join(missing)}")


def _bot_config() -> MatrixConfig:
    return MatrixConfig(
        homeserver=os.environ.get("HESTIA_MATRIX_HOMESERVER", "https://matrix.org"),
        user_id=os.environ.get("HESTIA_MATRIX_USER_ID", ""),
        device_id=os.environ.get("HESTIA_MATRIX_DEVICE_ID", "hestia-bot"),
        access_token=os.environ.get("HESTIA_MATRIX_ACCESS_TOKEN", ""),
        allowed_rooms=[os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]],
    )


def _tester_config() -> MatrixConfig:
    return MatrixConfig(
        homeserver=os.environ.get("HESTIA_MATRIX_HOMESERVER", "https://matrix.org"),
        user_id=os.environ.get("HESTIA_MATRIX_TESTER_USER_ID", ""),
        device_id=os.environ.get("HESTIA_MATRIX_TESTER_DEVICE_ID", "hestia-e2e-tester"),
        access_token=os.environ.get("HESTIA_MATRIX_TESTER_ACCESS_TOKEN", ""),
        allowed_rooms=[os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]],
    )


async def _wait_for_bot_response(
    tester: AsyncClient,
    room_id: str,
    bot_mxid: str,
    after_ts_ms: int,
    timeout: float = 30.0,
) -> str:
    """Poll room timeline for a substantive bot message after the trigger timestamp."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sync_response = await tester.sync(timeout=3000)
        if isinstance(sync_response, SyncResponse):
            room_info = sync_response.rooms.join.get(room_id)
            if room_info:
                for event in room_info.timeline.events:
                    if (
                        isinstance(event, RoomMessageText)
                        and event.sender == bot_mxid
                        and event.server_timestamp > after_ts_ms
                    ):
                        body = event.body.strip()
                        if body.lower() in {"thinking...", "thinking…"}:
                            # Matrix adapter may emit an interim status message first.
                            continue
                        return event.body
        await asyncio.sleep(0.5)
    raise TimeoutError(f"No bot response within {timeout}s")


@pytest.fixture
async def e2e_setup(tmp_path):
    """Bootstrap a disposable Hestia stack wired to a real Matrix adapter."""
    _skip_if_env_missing()

    db_path = tmp_path / "e2e.db"
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.connect()
    await db.create_tables()

    session_store = SessionStore(db)
    memory_store = MemoryStore(db)
    await memory_store.create_table()
    failure_store = FailureStore(db)
    await failure_store.create_table()
    trace_store = TraceStore(db)
    await trace_store.create_table()

    artifact_store = ArtifactStore(tmp_path / "artifacts")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    fake_inference = FakeInferenceClient()
    fake_policy = FakePolicyEngine()
    context_builder = ContextBuilder(fake_inference, fake_policy, body_factor=1.0)

    registry = ToolRegistry(artifact_store)
    registry.register(current_time)
    registry.register(http_get)
    registry.register(terminal)
    registry.register(make_read_file_tool([str(sandbox)]))
    registry.register(make_list_dir_tool([str(sandbox)]))
    registry.register(make_write_file_tool([str(sandbox)]))
    registry.register(make_read_artifact_tool(artifact_store))
    registry.register(make_save_memory_tool(memory_store))
    registry.register(make_list_memories_tool(memory_store))
    registry.register(make_search_memory_tool(memory_store))

    # epoch / skill_index not needed for these E2E tests

    yield {
        "db": db,
        "session_store": session_store,
        "memory_store": memory_store,
        "failure_store": failure_store,
        "trace_store": trace_store,
        "inference": fake_inference,
        "policy": fake_policy,
        "context_builder": context_builder,
        "registry": registry,
    }

    # Teardown: delete L12 tagged memories
    memories = await memory_store.list_memories(tag=E2E_MEMORY_TAG)
    for mem in memories:
        await memory_store.delete(mem.id)
    await db.close()


@pytest.mark.matrix_e2e
async def test_matrix_e2e_ping_pong(tmp_path, e2e_setup):
    """Send 'ping' from tester; expect bot to reply 'pong' via mock inference."""
    bot_cfg = _bot_config()
    tester_cfg = _tester_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]

    adapter = MatrixAdapter(bot_cfg)

    # Set deterministic mock response
    fake_inference = e2e_setup["inference"]
    fake_inference.responses = [
        ChatResponse(
            content="pong",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=5,
            completion_tokens=2,
            total_tokens=7,
        ),
    ]

    orchestrator = Orchestrator(
        inference=fake_inference,
        session_store=e2e_setup["session_store"],
        context_builder=e2e_setup["context_builder"],
        tool_registry=e2e_setup["registry"],
        policy=e2e_setup["policy"],
        confirm_callback=None,
        max_iterations=10,
        failure_store=e2e_setup["failure_store"],
        trace_store=e2e_setup["trace_store"],
    )

    async def on_message(platform_name: str, platform_user: str, text: str) -> None:
        session = await e2e_setup["session_store"].get_or_create_session(
            "matrix", platform_user
        )

        async def respond(response_text: str) -> None:
            await adapter.send_message(platform_user, response_text)

        await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content=text),
            respond_callback=respond,
            system_prompt="You are a helpful assistant.",
            platform=adapter,
            platform_user=platform_user,
        )

    await adapter.start(on_message)

    tester = AsyncClient(
        homeserver=tester_cfg.homeserver,
        user=tester_cfg.user_id,
        device_id=tester_cfg.device_id,
    )
    tester.access_token = tester_cfg.access_token

    try:
        # Wait for adapter initial sync to settle
        await asyncio.sleep(2)

        start_ts_ms = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "ping"},
        )
        assert isinstance(send_resp, RoomSendResponse), f"Send failed: {send_resp}"

        response_body = await _wait_for_bot_response(
            tester, room_id, bot_cfg.user_id, start_ts_ms, timeout=30.0
        )
        assert "pong" in response_body.lower(), f"Expected pong, got: {response_body}"
    finally:
        await adapter.stop()
        await tester.close()
        await fake_inference.close()


@pytest.mark.matrix_e2e
async def test_matrix_e2e_tool_visible_reply(tmp_path, e2e_setup):
    """Send 'what time is it?' and assert bot replies after calling current_time."""
    bot_cfg = _bot_config()
    tester_cfg = _tester_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]

    adapter = MatrixAdapter(bot_cfg)

    fake_inference = e2e_setup["inference"]
    fake_inference.responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="call_time_1",
                    name="current_time",
                    arguments={"timezone": "UTC"},
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="The current UTC time is available above.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=8,
            total_tokens=23,
        ),
    ]

    orchestrator = Orchestrator(
        inference=fake_inference,
        session_store=e2e_setup["session_store"],
        context_builder=e2e_setup["context_builder"],
        tool_registry=e2e_setup["registry"],
        policy=e2e_setup["policy"],
        confirm_callback=None,
        max_iterations=10,
        failure_store=e2e_setup["failure_store"],
        trace_store=e2e_setup["trace_store"],
    )

    async def on_message(platform_name: str, platform_user: str, text: str) -> None:
        session = await e2e_setup["session_store"].get_or_create_session(
            "matrix", platform_user
        )

        async def respond(response_text: str) -> None:
            await adapter.send_message(platform_user, response_text)

        await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content=text),
            respond_callback=respond,
            system_prompt="You are a helpful assistant.",
            platform=adapter,
            platform_user=platform_user,
        )

    await adapter.start(on_message)

    tester = AsyncClient(
        homeserver=tester_cfg.homeserver,
        user=tester_cfg.user_id,
        device_id=tester_cfg.device_id,
    )
    tester.access_token = tester_cfg.access_token

    try:
        await asyncio.sleep(2)

        start_ts_ms = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "what time is it?"},
        )
        assert isinstance(send_resp, RoomSendResponse), f"Send failed: {send_resp}"

        response_body = await _wait_for_bot_response(
            tester, room_id, bot_cfg.user_id, start_ts_ms, timeout=30.0
        )
        assert response_body, "Bot response was empty"
    finally:
        await adapter.stop()
        await tester.close()
        await fake_inference.close()
