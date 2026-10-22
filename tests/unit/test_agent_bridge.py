"""Unit tests for the Telegram ↔ Pi coding-agent bridge (L233).

PiRpcClient is tested against a fake subprocess transport (StreamReader-fed
stdout, capturing stdin); AgentBridge is tested against a fake adapter and a
fake PiRpcClient factory. No real ``pi``, ``git``, or ``kimi`` processes are
spawned.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Bot, Message, Update, User
from telegram.ext import Application

from hestia.config import TelegramConfig
from hestia.platforms.agent_bridge import AgentBridge, PiRpcClient, PiRpcError
from hestia.platforms.telegram_adapter import TelegramAdapter

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAdapter:
    """Minimal stand-in for TelegramAdapter's outbound surface."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.edits: list[tuple[str, str, str]] = []
        self.typing: list[tuple[str, bool]] = []
        self._next_id = 100

    async def send_message(self, user: str, text: str) -> str:
        self.sent.append((user, text))
        self._next_id += 1
        return str(self._next_id)

    async def edit_message(self, user: str, msg_id: str, text: str, **kwargs: Any) -> None:
        self.edits.append((user, msg_id, text))

    async def set_typing(self, user: str, typing: bool = True) -> None:
        self.typing.append((user, typing))


class FakeClient:
    """Fake PiRpcClient recording prompt traffic."""

    instances: list[FakeClient] = []

    def __init__(self) -> None:
        self.start_args: tuple[str, str, dict[str, str]] | None = None
        self.prompts: list[tuple[str, bool]] = []
        self.prompt_error: PiRpcError | None = None
        self.disposition = "started"
        self.closed = False
        self.abort_calls = 0
        self.handler: Any = None
        self.exit_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        FakeClient.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    def set_event_handler(self, handler: Any) -> None:
        self.handler = handler

    async def start(self, cwd: str, name: str, env: dict[str, str]) -> None:
        self.start_args = (cwd, name, env)

    async def prompt(self, message: str, *, steer: bool = False) -> dict[str, Any]:
        if self.prompt_error is not None:
            raise self.prompt_error
        self.prompts.append((message, steer))
        return {
            "type": "response",
            "command": "prompt",
            "success": True,
            "data": {"disposition": "queued" if steer else self.disposition},
        }

    async def abort(self) -> None:
        self.abort_calls += 1

    async def aclose(self) -> None:
        self.closed = True
        if not self.exit_future.done():
            self.exit_future.set_result(0)

    async def emit(self, record: dict[str, Any]) -> None:
        assert self.handler is not None
        await self.handler(record)

    def fail_child(self, rc: int = 1) -> None:
        if not self.exit_future.done():
            self.exit_future.set_result(rc)


def make_bridge(
    adapter: FakeAdapter,
    chats: list[str] | None = None,
    *,
    enabled: bool = True,
    workspace: str = "/tmp/fake-ws",
    head_resolver: Any = None,
    diff_resolver: Any = None,
    kimi_runner: Any = None,
) -> AgentBridge:
    config = TelegramConfig(
        bot_token="test:token",
        rate_limit_edits_seconds=0.01,
        agent_bridge_enabled=enabled,
        agent_bridge_chats=chats if chats is not None else ["42"],
        agent_bridge_workspace=workspace,
    )
    if head_resolver is None:

        async def head_resolver() -> str | None:  # type: ignore[no-redef]
            return None

    if diff_resolver is None:

        async def diff_resolver(pre: str, head: str) -> str | None:  # type: ignore[no-redef]
            return None

    if kimi_runner is None:

        async def kimi_runner(prompt: str, plan: bool) -> str | None:  # type: ignore[no-redef]
            return None

    return AgentBridge(
        adapter=adapter,
        config=config,
        client_factory=FakeClient,
        head_resolver=head_resolver,
        diff_resolver=diff_resolver,
        kimi_runner=kimi_runner,
    )


async def settle_run(
    client: FakeClient,
    *,
    final_text: str | None = "all done",
    aborted: bool = False,
) -> None:
    """Drive a fake run to agent_settled with one assistant answer."""
    if final_text is not None:
        await client.emit(
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": [{"type": "text", "text": final_text}]},
            }
        )
    await client.emit({"type": "agent_settled", "aborted": aborted})


@pytest.fixture
def adapter() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture(autouse=True)
def reset_fake_clients() -> None:
    FakeClient.reset()


# ---------------------------------------------------------------------------
# PiRpcClient framing and correlation (fake subprocess transport)
# ---------------------------------------------------------------------------


class _FakeStdin:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, payload: bytes) -> None:
        self.data += payload

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeProc:
    """Satisfies the PiProcess protocol with a feedable StreamReader."""

    def __init__(self) -> None:
        self.stdin: _FakeStdin = _FakeStdin()
        self.stdout = asyncio.StreamReader()
        self.stderr: asyncio.StreamReader | None = None
        self.terminated = False
        self.killed = False
        self._wait_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def wait(self) -> int:
        # Never block the fake: return the recorded result, else pretend a
        # clean exit so aclose() doesn't sit on its timeout.
        if self._wait_future.done():
            return self._wait_future.result()
        return 0

    def terminate(self) -> None:
        self.terminated = True
        if not self._wait_future.done():
            self._wait_future.set_result(-15)

    def kill(self) -> None:
        self.killed = True
        if not self._wait_future.done():
            self._wait_future.set_result(-9)

    def exit(self, rc: int = 0) -> None:
        if not self._wait_future.done():
            self._wait_future.set_result(rc)


def _spawn_returning(proc: FakeProc) -> Any:
    async def spawn(**kwargs: Any) -> FakeProc:  # noqa: ARG004
        return proc

    return spawn


class TestPiRpcClientFraming:
    @pytest.mark.asyncio
    async def test_splits_only_on_lf_and_keeps_unicode_separators(self) -> None:
        proc = FakeProc()
        events: list[dict[str, Any]] = []
        client = PiRpcClient(spawn=_spawn_returning(proc))
        client.set_event_handler(lambda record: _collect(events, record))

        await client.start(cwd="/ws", name="n", env={})
        # U+2028 and U+2029 inside a JSON string must not split the record.
        payload = {"type": "agent_start", "note": "line\u2028sep\u2029end"}
        proc.stdout.feed_data(json.dumps(payload).encode("utf-8") + b"\n")
        proc.stdout.feed_data(b'{"type":"turn_start"}\r\n')
        await asyncio.sleep(0.1)
        await client.aclose()

        assert [e.get("type") for e in events] == ["agent_start", "turn_start"]
        assert events[0]["note"] == "line\u2028sep\u2029end"

    @pytest.mark.asyncio
    async def test_records_may_span_reads(self) -> None:
        proc = FakeProc()
        events: list[dict[str, Any]] = []
        client = PiRpcClient(spawn=_spawn_returning(proc))
        client.set_event_handler(lambda record: _collect(events, record))
        await client.start(cwd="/ws", name="n", env={})

        record = json.dumps({"type": "tool_execution_start", "toolName": "bash"}).encode("utf-8")
        proc.stdout.feed_data(record[:10])
        await asyncio.sleep(0.05)
        proc.stdout.feed_data(record[10:] + b"\n")
        await asyncio.sleep(0.1)
        await client.aclose()

        assert [e.get("type") for e in events] == ["tool_execution_start"]

    @pytest.mark.asyncio
    async def test_prompt_correlates_response_by_id(self) -> None:
        proc = FakeProc()
        client = PiRpcClient(spawn=_spawn_returning(proc))
        await client.start(cwd="/ws", name="n", env={})

        task = asyncio.create_task(client.prompt("hello"))
        await asyncio.sleep(0.05)
        # The command on stdin must be a single LF-terminated JSON object.
        lines = bytes(proc.stdin.data).split(b"\n")
        assert lines[1] == b"", "exactly one command frame expected"
        command = json.loads(lines[0])
        assert command["type"] == "prompt"
        assert command["message"] == "hello"
        assert isinstance(command["id"], str) and command["id"]

        proc.stdout.feed_data(
            json.dumps(
                {
                    "id": command["id"],
                    "type": "response",
                    "command": "prompt",
                    "success": True,
                    "data": {"disposition": "started"},
                }
            ).encode("utf-8")
            + b"\n"
        )
        response = await asyncio.wait_for(task, timeout=1.0)
        assert response["data"]["disposition"] == "started"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_steer_sets_streaming_behavior(self) -> None:
        proc = FakeProc()
        client = PiRpcClient(spawn=_spawn_returning(proc))
        await client.start(cwd="/ws", name="n", env={})
        task = asyncio.create_task(client.prompt("wait, also do this", steer=True))
        await asyncio.sleep(0.05)
        command = json.loads(bytes(proc.stdin.data).split(b"\n")[0])
        assert command["streamingBehavior"] == "steer"
        proc.stdout.feed_data(
            json.dumps(
                {"id": command["id"], "type": "response", "command": "prompt", "success": True}
            ).encode("utf-8")
            + b"\n"
        )
        await asyncio.wait_for(task, timeout=1.0)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_prompt_failure_raises_and_eof_fails_pending(self) -> None:
        proc = FakeProc()
        client = PiRpcClient(spawn=_spawn_returning(proc))
        await client.start(cwd="/ws", name="n", env={})
        task = asyncio.create_task(client.prompt("hi"))
        await asyncio.sleep(0.05)
        command = json.loads(bytes(proc.stdin.data).split(b"\n")[0])
        proc.stdout.feed_data(
            json.dumps(
                {
                    "id": command["id"],
                    "type": "response",
                    "command": "prompt",
                    "success": False,
                    "error": "bad thing",
                }
            ).encode("utf-8")
            + b"\n"
        )
        with pytest.raises(PiRpcError, match="bad thing"):
            await asyncio.wait_for(task, timeout=1.0)

        # EOF fails any subsequent pending command promptly.
        pending = asyncio.create_task(client.prompt("again"))
        await asyncio.sleep(0.05)
        proc.stdout.feed_eof()
        with pytest.raises((PiRpcError, asyncio.TimeoutError)):
            await asyncio.wait_for(pending, timeout=1.0)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_exit_future_completes_on_eof(self) -> None:
        proc = FakeProc()
        client = PiRpcClient(spawn=_spawn_returning(proc))
        await client.start(cwd="/ws", name="n", env={})
        proc.stdout.feed_eof()
        rc = await asyncio.wait_for(client.exit_future, timeout=1.0)
        assert rc == 0
        await client.aclose()


async def _collect(events: list[dict[str, Any]], record: dict[str, Any]) -> None:
    events.append(record)


# ---------------------------------------------------------------------------
# AgentBridge routing and lifecycle
# ---------------------------------------------------------------------------


class TestBridgeRouting:
    @pytest.mark.asyncio
    async def test_allowlist_in_and_out(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter, chats=["42", "-100999"])
        assert bridge.should_route("42") is True
        assert bridge.should_route("-100999") is True
        assert bridge.should_route("43") is False

    @pytest.mark.asyncio
    async def test_disabled_config_routes_nothing(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter, enabled=False)
        assert bridge.should_route("42") is False

    @pytest.mark.asyncio
    async def test_first_message_spawns_child_with_fenced_env(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter, workspace="~/hestia-tg-agent")
        await bridge.handle("42", "build the thing")
        await asyncio.sleep(0)

        assert len(FakeClient.instances) == 1
        client = FakeClient.instances[0]
        cwd, name, env = client.start_args  # type: ignore[misc]
        assert cwd.endswith("hestia-tg-agent")  # expanduser applied
        assert "tg-42" in name
        assert env == {"PI_SESSION_ID": "42"}
        assert client.prompts == [("build the thing", False)]
        assert adapter.typing == [("42", True)]
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_second_message_after_settle_reuses_same_transport(
        self, adapter: FakeAdapter
    ) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "first task")
        client = FakeClient.instances[0]
        await settle_run(client, final_text="done one")
        await asyncio.sleep(0)

        await bridge.handle("42", "second task")
        await asyncio.sleep(0)
        assert len(FakeClient.instances) == 1
        assert client.prompts == [("first task", False), ("second task", False)]
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_mid_run_message_becomes_steering_on_same_transport(
        self, adapter: FakeAdapter
    ) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "long task")
        client = FakeClient.instances[0]
        assert client.prompts == [("long task", False)]

        await bridge.handle("42", "also do Y")
        assert client.prompts == [("long task", False), ("also do Y", True)]
        assert len(FakeClient.instances) == 1

        await settle_run(client, final_text="finished")
        await asyncio.sleep(0)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_spawn_failure_reports_and_does_not_crash(self, adapter: FakeAdapter) -> None:
        class BoomClient(FakeClient):
            async def start(self, cwd: str, name: str, env: dict[str, str]) -> None:
                raise FileNotFoundError("pi not found")

        BoomClient.reset()
        config = TelegramConfig(
            bot_token="t",
            agent_bridge_enabled=True,
            agent_bridge_chats=["42"],
            agent_bridge_workspace="/tmp/ws",
        )
        bridge = AgentBridge(adapter=adapter, config=config, client_factory=BoomClient)
        await bridge.handle("42", "hi")  # must not raise
        assert any("could not start" in text for _, text in adapter.sent)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_child_exit_marks_broken_and_respawns_on_next_message(
        self, adapter: FakeAdapter
    ) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "task one")
        first = FakeClient.instances[0]
        await settle_run(first, final_text="ok")
        await asyncio.sleep(0)

        first.fail_child(1)
        await asyncio.sleep(0.1)
        assert any("exited unexpectedly" in text for _, text in adapter.sent)

        await bridge.handle("42", "task two")
        await asyncio.sleep(0)
        assert len(FakeClient.instances) == 2
        second = FakeClient.instances[1]
        assert second.start_args is not None
        assert second.prompts == [("task two", False)]
        await settle_run(second, final_text="ok again")
        await asyncio.sleep(0)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_child_exit_mid_run_stops_typing_and_offers_restart(
        self, adapter: FakeAdapter
    ) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "task")
        client = FakeClient.instances[0]
        client.fail_child(1)
        await asyncio.sleep(0.1)
        assert adapter.typing[-1] == ("42", False)
        assert any("exited unexpectedly" in text for _, text in adapter.sent)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_aclose_terminates_children(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "task")
        await bridge.aclose()
        assert all(client.closed for client in FakeClient.instances)


class TestBridgeStatusUx:
    @pytest.mark.asyncio
    async def test_progress_edits_status_and_final_answer_is_new_message(
        self, adapter: FakeAdapter
    ) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "write docs")
        client = FakeClient.instances[0]

        await client.emit(
            {
                "type": "message_update",
                "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "Hel"},
            }
        )
        await asyncio.sleep(0.2)  # let the status editor flush
        await settle_run(client, final_text="Hello world")
        await asyncio.sleep(0)

        # Status edits happened on the status message id.
        assert adapter.edits, "expected at least one status edit"
        assert all(msg_id == "101" for _, msg_id, _ in adapter.edits)
        # The final answer went out as a NEW message, not an edit.
        assert ("42", "Hello world") in adapter.sent
        # Typing indicator turned off at settle.
        assert adapter.typing[-1] == ("42", False)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_retry_and_queue_events_map_to_queued_status(
        self, adapter: FakeAdapter
    ) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "go")
        client = FakeClient.instances[0]
        await client.emit(
            {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 2, "delayMs": 500}
        )
        await client.emit({"type": "queue_update", "steering": ["wait"], "followUp": []})
        await asyncio.sleep(0.2)
        assert any("queued" in text or "retrying" in text for _, _, text in adapter.edits)
        await settle_run(client)
        await asyncio.sleep(0)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_tool_events_update_status(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "go")
        client = FakeClient.instances[0]
        await client.emit(
            {"type": "tool_execution_start", "toolCallId": "c1", "toolName": "edit_file", "args": {}}
        )
        await asyncio.sleep(0.2)
        assert any("edit_file" in text for _, _, text in adapter.edits)
        await settle_run(client)
        await asyncio.sleep(0)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_failed_run_posts_failure_headline(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter)
        await bridge.handle("42", "go")
        client = FakeClient.instances[0]
        await client.emit(
            {"type": "auto_retry_end", "success": False, "attempt": 2, "finalError": "boom"}
        )
        await client.emit({"type": "agent_settled", "aborted": False})
        await asyncio.sleep(0)
        assert any("run failed" in text for _, _, text in adapter.edits)
        # No assistant text captured → no final answer message.
        assert not any(text == "whatever" for _, text in adapter.sent)
        await bridge.aclose()


# ---------------------------------------------------------------------------
# §4 Kimi reviewer loop
# ---------------------------------------------------------------------------


class TestReviewerLoop:
    def _resolvers(
        self, heads: list[str | None], diff: str | None = "diff --git a/x b/x"
    ) -> tuple[Any, Any, list[tuple[str, bool]]]:
        head_calls = iter(heads)

        async def head_resolver() -> str | None:
            return next(head_calls)

        async def diff_resolver(pre: str, head: str) -> str | None:
            return diff

        kimi_calls: list[tuple[str, bool]] = []

        async def kimi_runner(prompt: str, plan: bool) -> str | None:
            kimi_calls.append((prompt, plan))
            return "APPROVE — looks fine"

        return head_resolver, diff_resolver, kimi_calls, kimi_runner

    @pytest.mark.asyncio
    async def test_reviewer_skipped_when_head_unchanged(self, adapter: FakeAdapter) -> None:
        head_resolver, diff_resolver, kimi_calls, kimi_runner = self._resolvers(
            ["abc123", "abc123"]
        )
        bridge = make_bridge(
            adapter,
            head_resolver=head_resolver,
            diff_resolver=diff_resolver,
            kimi_runner=kimi_runner,
        )
        await bridge.handle("42", "change nothing")
        client = FakeClient.instances[0]
        await settle_run(client, final_text="no commits")
        await asyncio.sleep(0)
        assert kimi_calls == []
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_reviewer_fires_once_when_head_advances(self, adapter: FakeAdapter) -> None:
        head_resolver, diff_resolver, kimi_calls, kimi_runner = self._resolvers(
            ["abc123", "def456"]
        )
        bridge = make_bridge(
            adapter,
            head_resolver=head_resolver,
            diff_resolver=diff_resolver,
            kimi_runner=kimi_runner,
        )
        await bridge.handle("42", "make a commit")
        client = FakeClient.instances[0]
        await settle_run(client, final_text="committed")
        await asyncio.sleep(0)
        assert len(kimi_calls) == 1
        prompt, plan = kimi_calls[0]
        assert plan is True  # read-only review
        assert "diff --git" in prompt
        assert any("Kimi review" in text and "APPROVE" in text for _, text in adapter.sent)
        await bridge.aclose()

    def _fixed_head(self, value: str | None) -> Any:
        async def head_resolver() -> str | None:
            return value

        return head_resolver

    @pytest.mark.asyncio
    async def test_reviewer_failure_does_not_crash_bridge(self, adapter: FakeAdapter) -> None:
        head_resolver, diff_resolver, _kimi_calls, _ok_runner = self._resolvers(["a", "b", "b"])

        async def failing_kimi(prompt: str, plan: bool) -> str | None:
            raise RuntimeError("kimi exploded")

        bridge = make_bridge(
            adapter,
            head_resolver=head_resolver,
            diff_resolver=diff_resolver,
            kimi_runner=failing_kimi,
        )
        await bridge.handle("42", "task")
        client = FakeClient.instances[0]
        await settle_run(client, final_text="survived")
        await asyncio.sleep(0.1)
        # Bridge is still fully functional afterwards.
        await bridge.handle("42", "next task")
        assert len(FakeClient.instances) == 1
        assert client.prompts[-1] == ("next task", False)
        await settle_run(client, final_text="still alive")
        await asyncio.sleep(0)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_two_failed_runs_offer_kimi_and_yes_executes(
        self, adapter: FakeAdapter
    ) -> None:
        head_resolver = self._fixed_head("h")
        _head, diff_resolver, kimi_calls, kimi_runner = self._resolvers(["h", "h"])
        bridge = make_bridge(
            adapter,
            head_resolver=head_resolver,
            diff_resolver=diff_resolver,
            kimi_runner=kimi_runner,
        )

        # Two consecutive failed runs.
        for task in ("task one", "task two"):
            await bridge.handle("42", task)
            client = FakeClient.instances[0]
            await client.emit(
                {"type": "auto_retry_end", "success": False, "attempt": 2, "finalError": "boom"}
            )
            await client.emit({"type": "agent_settled", "aborted": False})
            await asyncio.sleep(0)

        assert any("Hand this task to Kimi" in text for _, text in adapter.sent)

        # "yes" reply runs kimi WITHOUT --plan (execution, not review).
        await bridge.handle("42", "yes")
        await asyncio.sleep(0)
        assert len(kimi_calls) == 1
        _prompt, plan = kimi_calls[0]
        assert plan is False
        # The stored task is the most recent failed run's task.
        assert any("task two" in prompt for prompt, _ in kimi_calls)
        await bridge.aclose()

    @pytest.mark.asyncio
    async def test_two_failed_runs_no_reply_clears_offer(self, adapter: FakeAdapter) -> None:
        bridge = make_bridge(adapter, head_resolver=lambda: _none())
        for task in ("task one", "task two"):
            await bridge.handle("42", task)
            client = FakeClient.instances[0]
            await client.emit({"type": "agent_settled", "aborted": True})
            await asyncio.sleep(0)
        assert any("Hand this task to Kimi" in text for _, text in adapter.sent)

        await bridge.handle("42", "no")
        await asyncio.sleep(0)
        assert any("continuing with the local agent" in text for _, text in adapter.sent)
        await bridge.aclose()


async def _none() -> str | None:
    return None


# ---------------------------------------------------------------------------
# TelegramAdapter integration (mock Application/Bot/Update pattern)
# ---------------------------------------------------------------------------


def _make_update(user_id: int, text: str, username: str = "tester") -> MagicMock:
    mock_update = MagicMock(spec=Update)
    mock_user = MagicMock(spec=User)
    mock_user.id = user_id
    mock_user.username = username
    mock_update.effective_user = mock_user
    mock_chat = MagicMock()
    mock_chat.type = "private"
    mock_update.effective_chat = mock_chat
    mock_message = MagicMock(spec=Message)
    mock_message.text = text
    mock_update.effective_message = mock_message
    return mock_update


class FakeBridge:
    """Stand-in for AgentBridge capturing adapter-level wiring."""

    def __init__(self, routed: set[str]) -> None:
        self.routed = routed
        self.handled: list[tuple[str, str]] = []
        self.closed = False

    def should_route(self, platform_user: str) -> bool:
        return platform_user in self.routed

    async def handle(self, platform_user: str, text: str) -> None:
        self.handled.append((platform_user, text))

    async def aclose(self) -> None:
        self.closed = True


class TestAdapterBridgeIntegration:
    @pytest.mark.asyncio
    async def test_bridge_routed_chat_bypasses_on_message(self) -> None:
        config = TelegramConfig(bot_token="test:token", allowed_users=["42"])
        tg_adapter = TelegramAdapter(config)
        bridge = FakeBridge(routed={"42"})
        tg_adapter.set_agent_bridge(bridge)

        on_message_called = False

        async def on_message(
            platform: str, user: str, text: str, sender: str | None, title: str | None = None
        ) -> None:
            nonlocal on_message_called
            on_message_called = True

        tg_adapter._on_message = on_message
        await tg_adapter._handle_message(_make_update(42, "fix the bug"), None)

        assert bridge.handled == [("42", "fix the bug")]
        assert on_message_called is False

    @pytest.mark.asyncio
    async def test_non_routed_chat_falls_through_to_on_message(self) -> None:
        config = TelegramConfig(bot_token="test:token", allowed_users=["42", "77"])
        tg_adapter = TelegramAdapter(config)
        tg_adapter.set_agent_bridge(FakeBridge(routed={"42"}))

        received: list[str] = []

        async def on_message(
            platform: str, user: str, text: str, sender: str | None, title: str | None = None
        ) -> None:
            received.append(text)

        tg_adapter._on_message = on_message
        await tg_adapter._handle_message(_make_update(77, "normal chat"), None)

        assert received == ["normal chat"]

    @pytest.mark.asyncio
    async def test_stop_closes_bridge(self) -> None:
        config = TelegramConfig(bot_token="test:token")
        tg_adapter = TelegramAdapter(config)
        bridge = FakeBridge(routed={"42"})
        tg_adapter.set_agent_bridge(bridge)

        mock_app = AsyncMock(spec=Application)
        mock_app.updater = AsyncMock()
        mock_bot = AsyncMock(spec=Bot)
        mock_app.bot = mock_bot
        tg_adapter._app = mock_app

        await tg_adapter.stop()

        assert bridge.closed is True

    @pytest.mark.asyncio
    async def test_workflow_reply_still_resolves_before_bridge(self) -> None:
        """A pending workflow response must be consumed before bridge routing."""
        from hestia.workflows.response_store import DEFAULT_RESPONSE_STORE

        config = TelegramConfig(bot_token="test:token", allowed_users=["42"])
        tg_adapter = TelegramAdapter(config)
        bridge = FakeBridge(routed={"42"})
        tg_adapter.set_agent_bridge(bridge)

        request_id, _future = DEFAULT_RESPONSE_STORE.create(
            "telegram", "42", timeout_seconds=60.0
        )
        mock_update = _make_update(42, "a")
        await tg_adapter._handle_message(mock_update, None)

        assert bridge.handled == []
        DEFAULT_RESPONSE_STORE.cancel(request_id)


class _RaceThenSteerClient(FakeClient):
    """Raises Pi's mid-stream rejection once, then accepts as steer."""

    def __init__(self) -> None:
        super().__init__()
        self.raced = False

    async def prompt(self, message: str, *, steer: bool = False) -> dict[str, Any]:
        if not steer and not self.raced:
            self.raced = True
            raise PiRpcError(
                "Agent is already processing. Specify streamingBehavior "
                "('steer' or 'followUp') to queue the message."
            )
        return await super().prompt(message, steer=steer)


class TestMidRunRace:
    @pytest.mark.asyncio
    async def test_already_processing_retries_as_steer(self) -> None:
        adapter = FakeAdapter()
        bridge = make_bridge(adapter, workspace="/tmp/fake-ws-race")
        bridge._client_factory = _RaceThenSteerClient  # type: ignore[assignment]
        await bridge.handle("42", "fix it")
        client = _RaceThenSteerClient.instances[-1]
        # The user's message must survive as a steer, not be dropped.
        assert client.prompts == [("fix it", True)]
        await settle_run(client)
        await bridge.aclose()


class _FakeKimiProc:
    def __init__(self, stdout: bytes, rc: int = 0) -> None:
        self._stdout = stdout
        self.returncode = rc

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:  # pragma: no cover - timeout path unused here
        pass


class TestRunKimiCommandShape:
    def _make_bridge(self, monkeypatch: Any, tmp_path: Any, agent_file: Any) -> AgentBridge:
        adapter = FakeAdapter()
        bridge = make_bridge(adapter, workspace="/tmp/fake-ws-kimi")
        commands: list[list[str]] = []

        async def fake_exec(*args: Any, **kwargs: Any) -> _FakeKimiProc:
            commands.append(list(args))
            return _FakeKimiProc(b'{"type":"text","text":"LGTM"}\n')

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setenv("TG_REVIEWER_AGENT_FILE", str(agent_file))
        self.commands = commands
        return bridge

    @pytest.mark.asyncio
    async def test_review_uses_agent_file_not_plan(self, monkeypatch: Any, tmp_path: Any) -> None:
        agent_file = tmp_path / "reviewer.md"
        agent_file.write_text("---\ndescription: d\ntools: [Read]\n---\nbody")
        bridge = self._make_bridge(monkeypatch, tmp_path, agent_file)

        result = await bridge._run_kimi("review this", plan=True)

        assert result == "LGTM"
        (cmd,) = self.commands
        assert "--plan" not in cmd
        assert "--session" not in cmd
        assert "--agent-file" in cmd
        assert cmd[cmd.index("--agent-file") + 1] == str(agent_file)

    @pytest.mark.asyncio
    async def test_exec_has_no_plan_no_session_no_agent_file(
        self, monkeypatch: Any, tmp_path: Any
    ) -> None:
        agent_file = tmp_path / "reviewer.md"
        agent_file.write_text("---\ndescription: d\ntools: [Read]\n---\nbody")
        bridge = self._make_bridge(monkeypatch, tmp_path, agent_file)

        result = await bridge._run_kimi("do this", plan=False)

        assert result == "LGTM"
        (cmd,) = self.commands
        assert "--plan" not in cmd
        assert "--session" not in cmd
        assert "--agent-file" not in cmd

    @pytest.mark.asyncio
    async def test_missing_agent_file_refuses_review(
        self, monkeypatch: Any, tmp_path: Any
    ) -> None:
        missing = tmp_path / "nope.md"
        bridge = self._make_bridge(monkeypatch, tmp_path, missing)

        result = await bridge._run_kimi("review this", plan=True)

        assert result is None
        assert self.commands == []  # never spawned
