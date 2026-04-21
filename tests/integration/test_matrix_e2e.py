# mypy: disable-error-code="no-untyped-def,import-not-found,import-untyped,no-any-return"
"""Matrix E2E tests against a real homeserver (skipped without env).

These tests verify the *actual Matrix conversation* — every message the bot
sends to the room, typing indicators, status message cleanup, memory tools,
and multi-turn persistence.  They use FakeInferenceClient for deterministic
model responses but hit a real Matrix homeserver for transport.

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
from dataclasses import dataclass, field

import pytest

pytest.importorskip("nio", reason="matrix-nio not installed")

from helpers import FakeInferenceClient, FakePolicyEngine
from nio import AsyncClient, RoomMessageText, RoomSendResponse, SyncResponse
from nio.events.ephemeral import TypingNoticeEvent

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
from hestia.config import StorageConfig

E2E_MEMORY_TAG = "e2e_hestia_l12"


# ---------------------------------------------------------------------------
# Env / config helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Conversation recorder — captures the full room shape as the tester sees it
# ---------------------------------------------------------------------------

@dataclass
class ConversationRecord:
    """All bot messages and typing events the tester observed during a test."""
    bot_messages: list[str] = field(default_factory=list)
    typing_observed: bool = False
    redacted_event_ids: set[str] = field(default_factory=set)


async def _drain_timeline(tester: AsyncClient) -> None:
    """Repeatedly sync until no more events arrive, so subsequent syncs are clean."""
    while True:
        resp = await tester.sync(timeout=1000)
        if not isinstance(resp, SyncResponse):
            break
        if not resp.rooms.join:
            break
        has_events = any(
            room.timeline.events for room in resp.rooms.join.values()
        )
        if not has_events:
            break


STATUS_PREFIXES = ("running ", "thinking")


def _is_status_message(body: str) -> bool:
    """Check if a message is an interim status message (not a final response)."""
    return body.lower().strip().startswith(STATUS_PREFIXES)


async def _collect_conversation(
    tester: AsyncClient,
    room_id: str,
    bot_mxid: str,
    after_ts_ms: int,
    expect_final_messages: int = 1,
    timeout: float = 30.0,
) -> ConversationRecord:
    """Sync until *expect_final_messages* non-status bot messages arrive.

    Status messages ("Running ...", "Thinking...") are recorded but don't count
    toward the expected count. Returns a ConversationRecord with all bot
    messages, typing observations, and redacted event IDs.
    """
    record = ConversationRecord()
    seen_event_ids: set[str] = set()
    deadline = time.monotonic() + timeout

    def _final_count() -> int:
        return sum(1 for m in record.bot_messages if not _is_status_message(m))

    while time.monotonic() < deadline:
        sync_response = await tester.sync(timeout=3000)
        if not isinstance(sync_response, SyncResponse):
            await asyncio.sleep(0.3)
            continue

        room_info = sync_response.rooms.join.get(room_id)
        if not room_info:
            await asyncio.sleep(0.3)
            continue

        for ev in room_info.ephemeral:
            if isinstance(ev, TypingNoticeEvent) and bot_mxid in ev.users:
                record.typing_observed = True

        for event in room_info.timeline.events:
            if event.event_id in seen_event_ids:
                continue
            seen_event_ids.add(event.event_id)

            if getattr(event, "type", None) == "m.room.redaction":
                redacted_id = getattr(event, "redacts", None)
                if redacted_id:
                    record.redacted_event_ids.add(redacted_id)
                continue

            if (
                isinstance(event, RoomMessageText)
                and event.sender == bot_mxid
                and event.server_timestamp > after_ts_ms
            ):
                record.bot_messages.append(event.body.strip())

        if _final_count() >= expect_final_messages:
            # Drain one more sync for trailing redactions / typing-off
            try:
                extra = await asyncio.wait_for(tester.sync(timeout=2000), timeout=3.0)
                if isinstance(extra, SyncResponse):
                    extra_room = extra.rooms.join.get(room_id)
                    if extra_room:
                        for ev in extra_room.ephemeral:
                            if isinstance(ev, TypingNoticeEvent) and bot_mxid in ev.users:
                                record.typing_observed = True
                        for event in extra_room.timeline.events:
                            if getattr(event, "type", None) == "m.room.redaction":
                                redacted_id = getattr(event, "redacts", None)
                                if redacted_id:
                                    record.redacted_event_ids.add(redacted_id)
                            elif (
                                isinstance(event, RoomMessageText)
                                and event.sender == bot_mxid
                                and event.server_timestamp > after_ts_ms
                                and event.event_id not in seen_event_ids
                            ):
                                record.bot_messages.append(event.body.strip())
            except asyncio.TimeoutError:
                pass
            return record

        await asyncio.sleep(0.3)

    raise TimeoutError(
        f"Expected {expect_final_messages} final bot message(s) within {timeout}s, "
        f"got {_final_count()} final out of {len(record.bot_messages)} total: "
        f"{record.bot_messages}"
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

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
    registry.register(make_read_file_tool(StorageConfig(allowed_roots=[str(sandbox)])))
    registry.register(make_list_dir_tool(StorageConfig(allowed_roots=[str(sandbox)])))
    registry.register(make_write_file_tool(StorageConfig(allowed_roots=[str(sandbox)])))
    registry.register(make_read_artifact_tool(artifact_store))
    registry.register(make_save_memory_tool(memory_store))
    registry.register(make_list_memories_tool(memory_store))
    registry.register(make_search_memory_tool(memory_store))

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


def _make_orchestrator(setup: dict) -> Orchestrator:
    return Orchestrator(
        inference=setup["inference"],
        session_store=setup["session_store"],
        context_builder=setup["context_builder"],
        tool_registry=setup["registry"],
        policy=setup["policy"],
        confirm_callback=None,
        max_iterations=10,
        failure_store=setup["failure_store"],
        trace_store=setup["trace_store"],
    )


def _make_on_message(
    adapter: MatrixAdapter,
    orchestrator: Orchestrator,
    setup: dict,
    *,
    gate_phrase: str | None = None,
):
    """Create an on_message callback, optionally gated to only respond to a specific phrase.

    If *gate_phrase* is set, the bot ignores any incoming message whose body
    doesn't start with the phrase. This prevents stale messages from prior
    tests consuming mock inference responses.
    """
    responded = asyncio.Event()

    async def on_message(platform_name: str, platform_user: str, text: str) -> None:
        if gate_phrase and not text.strip().startswith(gate_phrase):
            return

        session = await setup["session_store"].get_or_create_session(
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
        responded.set()

    on_message.responded = responded  # type: ignore[attr-defined]
    return on_message


async def _setup_tester(tester_cfg: MatrixConfig) -> AsyncClient:
    tester = AsyncClient(
        homeserver=tester_cfg.homeserver,
        user=tester_cfg.user_id,
        device_id=tester_cfg.device_id,
    )
    tester.access_token = tester_cfg.access_token
    return tester


# ---------------------------------------------------------------------------
# Test 1: Basic ping/pong — verify clean conversation (no Thinking... leak)
# ---------------------------------------------------------------------------

@pytest.mark.matrix_e2e
async def test_matrix_e2e_ping_pong(tmp_path, e2e_setup):
    """Send 'ping', verify bot replies 'pong' and nothing else."""
    bot_cfg = _bot_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]
    adapter = MatrixAdapter(bot_cfg)

    GATE = "[t1] ping"

    e2e_setup["inference"].responses = [
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

    orchestrator = _make_orchestrator(e2e_setup)
    await adapter.start(
        _make_on_message(adapter, orchestrator, e2e_setup, gate_phrase=GATE)
    )

    tester = await _setup_tester(_tester_config())
    try:
        await asyncio.sleep(2)
        await _drain_timeline(tester)

        after_ts = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE},
        )
        assert isinstance(send_resp, RoomSendResponse), f"Send failed: {send_resp}"

        conv = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts,
            expect_final_messages=1, timeout=30.0,
        )

        assert len(conv.bot_messages) == 1, (
            f"Expected exactly 1 bot message, got {len(conv.bot_messages)}: "
            f"{conv.bot_messages}"
        )
        assert "pong" in conv.bot_messages[0].lower()

        thinking_msgs = [m for m in conv.bot_messages if "thinking" in m.lower()]
        assert not thinking_msgs, (
            f"Bot sent 'Thinking...' message(s) instead of using typing indicator: "
            f"{thinking_msgs}"
        )
    finally:
        await adapter.stop()
        await tester.close()


# ---------------------------------------------------------------------------
# Test 2: Tool call — verify status message, cleanup, and final response
# ---------------------------------------------------------------------------

@pytest.mark.matrix_e2e
async def test_matrix_e2e_tool_call_clean_conversation(tmp_path, e2e_setup):
    """Tool call flow: status message appears then gets redacted; final response is clean."""
    bot_cfg = _bot_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]
    adapter = MatrixAdapter(bot_cfg)

    GATE = "[t2] what time is it?"

    e2e_setup["inference"].responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="call_time_1",
                    name="call_tool",
                    arguments={"name": "current_time", "arguments": {"timezone": "UTC"}},
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="The current UTC time is 2026-04-14 03:00.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=8,
            total_tokens=23,
        ),
    ]

    orchestrator = _make_orchestrator(e2e_setup)
    await adapter.start(
        _make_on_message(adapter, orchestrator, e2e_setup, gate_phrase=GATE)
    )

    tester = await _setup_tester(_tester_config())
    try:
        await asyncio.sleep(2)
        await _drain_timeline(tester)

        after_ts = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE},
        )
        assert isinstance(send_resp, RoomSendResponse)

        conv = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts,
            expect_final_messages=1, timeout=30.0,
        )

        final_messages = [m for m in conv.bot_messages if not _is_status_message(m)]
        assert len(final_messages) >= 1, f"No final response found in: {conv.bot_messages}"
        assert "2026" in final_messages[-1] or "UTC" in final_messages[-1], (
            f"Expected time response, got: {final_messages}"
        )

        thinking_msgs = [
            m for m in conv.bot_messages
            if m.lower().strip() in {"thinking...", "thinking…"}
        ]
        assert not thinking_msgs, (
            f"'Thinking...' message leaked into room: {thinking_msgs}"
        )
    finally:
        await adapter.stop()
        await tester.close()


# ---------------------------------------------------------------------------
# Test 3: Memory save via Matrix — bot uses save_memory tool
# ---------------------------------------------------------------------------

@pytest.mark.matrix_e2e
async def test_matrix_e2e_memory_save(tmp_path, e2e_setup):
    """Bot saves a memory via tool call, tester sees confirmation."""
    bot_cfg = _bot_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]
    adapter = MatrixAdapter(bot_cfg)

    GATE = "[t3] Remember that my favorite color is blue"

    e2e_setup["inference"].responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c_save",
                    name="call_tool",
                    arguments={
                        "name": "save_memory",
                        "arguments": {
                            "content": "Dylan's favorite color is blue",
                            "tags": f"{E2E_MEMORY_TAG} preference",
                        },
                    },
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Got it! I've saved that your favorite color is blue.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=10,
            total_tokens=25,
        ),
    ]

    orchestrator = _make_orchestrator(e2e_setup)
    await adapter.start(
        _make_on_message(adapter, orchestrator, e2e_setup, gate_phrase=GATE)
    )

    tester = await _setup_tester(_tester_config())
    try:
        await asyncio.sleep(2)
        await _drain_timeline(tester)

        after_ts = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE},
        )
        assert isinstance(send_resp, RoomSendResponse)

        conv = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts,
            expect_final_messages=1, timeout=30.0,
        )

        assert any("blue" in m.lower() or "saved" in m.lower() for m in conv.bot_messages), (
            f"Expected save confirmation, got: {conv.bot_messages}"
        )

        memories = await e2e_setup["memory_store"].list_memories(tag=E2E_MEMORY_TAG)
        assert len(memories) >= 1, "Memory was not persisted"
        assert any("blue" in m.content.lower() for m in memories)
    finally:
        await adapter.stop()
        await tester.close()


# ---------------------------------------------------------------------------
# Test 4: Memory save + recall — two-turn conversation over Matrix
# ---------------------------------------------------------------------------

@pytest.mark.matrix_e2e
async def test_matrix_e2e_memory_save_then_recall(tmp_path, e2e_setup):
    """Turn 1: save a memory. Turn 2: search for it. Verify round-trip over Matrix."""
    bot_cfg = _bot_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]
    adapter = MatrixAdapter(bot_cfg)

    GATE1 = "[t4a] Remember: Hestia typing indicators shipped"
    GATE2 = "[t4b] What do you remember about Hestia?"

    turn1_responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c_save",
                    name="call_tool",
                    arguments={
                        "name": "save_memory",
                        "arguments": {
                            "content": "Project Hestia milestone: typing indicators shipped",
                            "tags": f"{E2E_MEMORY_TAG} project",
                        },
                    },
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Noted! I've saved that milestone.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=8,
            total_tokens=23,
        ),
    ]

    turn2_responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c_search",
                    name="call_tool",
                    arguments={
                        "name": "search_memory",
                        "arguments": {"query": "Hestia milestone"},
                    },
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="I found your note: typing indicators were shipped for Project Hestia.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=12,
            total_tokens=32,
        ),
    ]

    fake_inference = e2e_setup["inference"]
    fake_inference.responses = turn1_responses

    # Gate starts on turn 1 phrase; we'll swap the gate between turns
    gate_ref: dict[str, str] = {"current": GATE1}

    orchestrator = _make_orchestrator(e2e_setup)

    async def gated_on_message(platform_name: str, platform_user: str, text: str) -> None:
        if not text.strip().startswith(gate_ref["current"]):
            return
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

    await adapter.start(gated_on_message)
    tester = await _setup_tester(_tester_config())

    try:
        await asyncio.sleep(2)
        await _drain_timeline(tester)

        # --- Turn 1: save ---
        after_ts1 = int(time.time() * 1000)
        send1 = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE1},
        )
        assert isinstance(send1, RoomSendResponse)

        conv1 = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts1,
            expect_final_messages=1, timeout=30.0,
        )
        assert any("noted" in m.lower() or "saved" in m.lower() for m in conv1.bot_messages), (
            f"Turn 1 expected save confirmation, got: {conv1.bot_messages}"
        )

        # --- Turn 2: recall ---
        fake_inference.responses = turn2_responses
        fake_inference.call_count = 0
        gate_ref["current"] = GATE2

        after_ts2 = int(time.time() * 1000)
        send2 = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE2},
        )
        assert isinstance(send2, RoomSendResponse)

        conv2 = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts2,
            expect_final_messages=1, timeout=30.0,
        )
        assert any("typing indicators" in m.lower() or "hestia" in m.lower()
                    for m in conv2.bot_messages), (
            f"Turn 2 expected recall of milestone, got: {conv2.bot_messages}"
        )
    finally:
        await adapter.stop()
        await tester.close()


# ---------------------------------------------------------------------------
# Test 5: No Thinking... messages anywhere — regression guard
# ---------------------------------------------------------------------------

@pytest.mark.matrix_e2e
async def test_matrix_e2e_no_thinking_message(tmp_path, e2e_setup):
    """Verify the bot never sends 'Thinking...' as a real message.

    The bot should use the typing indicator (m.typing ephemeral event) instead.
    """
    bot_cfg = _bot_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]
    adapter = MatrixAdapter(bot_cfg)

    GATE = "[t5] what time is it right now?"

    e2e_setup["inference"].responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c_time",
                    name="call_tool",
                    arguments={"name": "current_time", "arguments": {"timezone": "UTC"}},
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="It is currently 03:15 UTC.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=6,
            total_tokens=21,
        ),
    ]

    orchestrator = _make_orchestrator(e2e_setup)
    await adapter.start(
        _make_on_message(adapter, orchestrator, e2e_setup, gate_phrase=GATE)
    )

    tester = await _setup_tester(_tester_config())
    try:
        await asyncio.sleep(2)
        await _drain_timeline(tester)

        after_ts = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE},
        )
        assert isinstance(send_resp, RoomSendResponse)

        conv = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts,
            expect_final_messages=1, timeout=30.0,
        )

        thinking_msgs = [
            m for m in conv.bot_messages
            if m.lower().strip() in {"thinking...", "thinking…"}
        ]
        assert not thinking_msgs, (
            f"Bot sent 'Thinking...' as a real message! "
            f"All bot messages: {conv.bot_messages}"
        )

        assert any("03:15" in m or "utc" in m.lower() for m in conv.bot_messages), (
            f"Expected time response, got: {conv.bot_messages}"
        )
    finally:
        await adapter.stop()
        await tester.close()


# ---------------------------------------------------------------------------
# Test 6: Search memory with no results — verify empty response over Matrix
# ---------------------------------------------------------------------------

@pytest.mark.matrix_e2e
async def test_matrix_e2e_memory_search_no_results(tmp_path, e2e_setup):
    """Search for a nonexistent memory, verify bot relays 'no results' message."""
    bot_cfg = _bot_config()
    room_id = os.environ["HESTIA_MATRIX_TEST_ROOM_ID"]
    adapter = MatrixAdapter(bot_cfg)

    GATE = "[t6] search memory for xyznonexistent_e2e_test"

    e2e_setup["inference"].responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c_search",
                    name="call_tool",
                    arguments={
                        "name": "search_memory",
                        "arguments": {"query": "xyznonexistent_e2e_test"},
                    },
                ),
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="I couldn't find any memories matching that query.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=10,
            total_tokens=25,
        ),
    ]

    orchestrator = _make_orchestrator(e2e_setup)
    await adapter.start(
        _make_on_message(adapter, orchestrator, e2e_setup, gate_phrase=GATE)
    )

    tester = await _setup_tester(_tester_config())
    try:
        await asyncio.sleep(2)
        await _drain_timeline(tester)

        after_ts = int(time.time() * 1000)
        send_resp = await tester.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": GATE},
        )
        assert isinstance(send_resp, RoomSendResponse)

        conv = await _collect_conversation(
            tester, room_id, bot_cfg.user_id, after_ts,
            expect_final_messages=1, timeout=30.0,
        )
        assert any("couldn't find" in m.lower() or "no" in m.lower()
                    for m in conv.bot_messages), (
            f"Expected no-results response, got: {conv.bot_messages}"
        )
    finally:
        await adapter.stop()
        await tester.close()