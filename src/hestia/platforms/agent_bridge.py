"""Telegram ↔ coding-agent bridge (L233; L251 adds a per-chat Kimi CLI backend).

Spawns one persistent ``pi --mode rpc`` child per allowlisted chat (or, when
the chat's stored backend is ``kimi``, one-shot ``kimi -p`` subprocess runs
resumed via a persisted session id) and routes messages to it, with
progressive status UX on Telegram and a Kimi reviewer loop (§4). The Pi RPC
protocol is version-exact per the installed
``@earendil-works/pi-coding-agent`` docs (rpc.md / rpc-commands.md / json.md):
strict LF-delimited JSONL on byte streams, correlated command ids, and
``agent_settled`` as the run-completion signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from hestia.config import TelegramConfig
from hestia.platforms.tg_agent_instructions import AGENT_WORKSPACE_AGENTS_MD

if TYPE_CHECKING:
    from hestia.persistence.chat_settings import ChatSettingsStore
    from hestia.platforms.telegram_adapter import TelegramAdapter

logger = logging.getLogger(__name__)

_READ_CHUNK = 65536
_COMMAND_TIMEOUT = 30.0
_CLOSE_TIMEOUT = 10.0
_KILL_TIMEOUT = 5.0
_KIMI_TIMEOUT = 900.0
_DIFF_MAX_CHARS = 100_000
_STREAM_TAIL_CHARS = 400
_REVIEW_MAX_CHARS = 3500
# Coarse throttle above the adapter's per-message edit rate limit so token
# floods do not pile up edit calls.
_STATUS_EDIT_INTERVAL = 2.0

_YES_REPLIES = {"yes", "y", "yeah", "yep", "sure"}
_NO_REPLIES = {"no", "n", "nope"}

# Per-chat selectable coding-agent backends (L251).
BACKEND_PI = "pi"
BACKEND_KIMI = "kimi"
# Printed by ``kimi -p`` on stdout as the last line of a run; the captured
# token (e.g. "session_<uuid>") is passed verbatim to ``-S`` on later turns.
_KIMI_RESUME_RE = re.compile(r"^To resume this session:\s+\S+\s+-r\s+(\S+)\s*$")
_KIMI_VERSION_RE = re.compile(r"^kimi version \S+\s*$")

# Read-only reviewer agent for kimi (--agent-file). kimi 2.2.0 rejects
# --prompt+--plan, so review mode is enforced by the agent file allowlist
# (Read/Grep/Glob only; re-checked before every tool execution).
_DEFAULT_REVIEWER_AGENT = "~/.kimi-code/agents/tg-reviewer.md"

_REVIEW_INSTRUCTIONS = (
    "You are reviewing commits just produced by an automated coding agent in the "
    "workspace {workspace!r}. The diff below spans exactly the new commits. "
    "Review for correctness, security issues, and spec compliance. Verdict first "
    "(APPROVE or REQUEST_CHANGES), then concise bullet points.\n\n```diff\n{diff}\n```"
)

_EXEC_INSTRUCTIONS = (
    "You are taking over a task from an automated coding agent that failed twice "
    "in the workspace {workspace!r}. Complete the user's task directly. Work only "
    "inside the workspace. Task:\n\n{task}"
)


class PiRpcError(RuntimeError):
    """A Pi RPC command failed, timed out, or the child is unavailable."""


class PiProcess(Protocol):
    """Structural type of the subprocess handle PiRpcClient drives.

    ``asyncio.subprocess.Process`` satisfies this; tests inject fakes.
    """

    stdin: asyncio.StreamWriter | None
    stdout: asyncio.StreamReader | None
    stderr: asyncio.StreamReader | None

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


SpawnFn = Callable[..., Awaitable[PiProcess]]
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]
HeadResolver = Callable[[Path], Awaitable[str | None]]
DiffResolver = Callable[[Path, str, str], Awaitable[str | None]]
KimiRunner = Callable[[str, bool], Awaitable[str | None]]
CommandRunner = Callable[..., Awaitable[tuple[int, str]]]

# Deploy-request marker the agent writes into its own workspace to ask the
# bridge to review + deploy a repair. See tg_agent_instructions.AGENTS_MD.
_DEPLOY_REQUEST_REL = Path(".repair") / "deploy-request.json"
# Auto-deploy is off unless the service environment explicitly enables it.
_DEPLOY_ENV_FLAG = "TG_AGENT_AUTO_DEPLOY"
# Escape hatch for tests/legacy: all chats share the configured workspace root.
_FLAT_WORKSPACE_ENV = "TG_AGENT_FLAT_WORKSPACE"
_DEPLOY_ALLOWED_REPOS = (
    os.path.expanduser("~/Hestia-runtime"),
    os.path.expanduser("~/Hestia"),
)
_DEPLOY_HEALTH_TIMEOUT_SECONDS = 60.0
_DEPLOY_HEALTH_INTERVAL_SECONDS = 3.0
_APPROVE_RE = re.compile(r"^\W*APPROVE", re.IGNORECASE | re.DOTALL)

_REPAIR_REVIEW_INSTRUCTIONS = (
    "You are reviewing an autonomous repair to the Hestia codebase.\n"
    "Repo: {repo!r}\n"
    "Agent's summary: {summary}\n\n"
    "The diff below spans exactly the repair commits. Review for correctness, "
    "security issues (especially credential exposure), and whether the change "
    "plausibly fixes the summarized problem without obvious regressions. "
    "Verdict first (APPROVE or REQUEST_CHANGES), then concise bullets.\n\n"
    "```diff\n{diff}\n```"
)


def _verdict_is_approval(verdict: str) -> bool:
    """True when the reviewer's verdict starts with APPROVE (markdown-tolerant)."""
    return bool(_APPROVE_RE.match(verdict.strip()))


async def _run_command(*args: str, timeout: float = 60.0) -> tuple[int, str]:
    """Run a command, merging stderr into stdout. Returns (rc, output)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return 124, "command timed out"
    return proc.returncode or 0, stdout.decode("utf-8", "replace")


async def _default_spawn(cwd: str, name: str, env: dict[str, str]) -> PiProcess:
    """Spawn ``pi --mode rpc`` with a fenced environment overlay."""
    full_env = dict(os.environ)
    full_env.update(env)
    return await asyncio.create_subprocess_exec(
        "pi",
        "--mode",
        "rpc",
        "--name",
        name,
        cwd=cwd,
        env=full_env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class PiRpcClient:
    """Asyncio JSONL client for one persistent ``pi --mode rpc`` child.

    Framing is strict per the Pi docs: stdout is read as raw bytes and records
    split only on LF, with one optional trailing CR stripped. Unicode line/paragraph
    separators (U+2028/U+2029) inside JSON strings are never treated as boundaries.
    A dedicated reader task consumes stdout continuously — Pi honors backpressure,
    so a client that stops reading stalls the child. Events are dispatched to the
    registered handler as fire-and-forget tasks to keep the reader unblocked.
    """

    def __init__(self, spawn: SpawnFn | None = None) -> None:
        self._spawn = spawn or _default_spawn
        self._proc: PiProcess | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._event_handler: EventHandler | None = None
        self.exit_future: asyncio.Future[int] = asyncio.get_event_loop().create_future()

    def set_event_handler(self, handler: EventHandler | None) -> None:
        """Register the async handler for non-response session events."""
        self._event_handler = handler

    async def start(self, cwd: str, name: str, env: dict[str, str]) -> None:
        """Spawn the child and begin reading stdout."""
        if self._proc is not None:
            raise PiRpcError("PiRpcClient already started")
        proc = await self._spawn(cwd=cwd, name=name, env=env)
        self._proc = proc
        self._reader_task = asyncio.create_task(self._read_loop())
        if proc.stderr is not None:
            self._stderr_task = asyncio.create_task(self._drain_stderr(proc))

    @property
    def started(self) -> bool:
        return self._proc is not None

    async def prompt(self, message: str, *, steer: bool = False) -> dict[str, Any]:
        """Send a prompt command; returns the correlated response record.

        With ``steer=True`` the command carries ``streamingBehavior: "steer"``
        (required by Pi when the agent is already streaming).
        """
        command: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "type": "prompt",
            "message": message,
        }
        if steer:
            command["streamingBehavior"] = "steer"
        response = await self._command(command)
        if not response.get("success", False):
            raise PiRpcError(str(response.get("error", "prompt rejected")))
        return response

    async def abort(self) -> None:
        """Abort the current run; errors are swallowed (best effort)."""
        with contextlib.suppress(PiRpcError):
            await self._command({"id": uuid.uuid4().hex[:12], "type": "abort"})

    async def aclose(self) -> None:
        """Close stdin, await an orderly exit, then escalate to kill."""
        proc = self._proc
        self._proc = None
        if proc is not None and proc.stdin is not None:
            with contextlib.suppress(Exception):
                proc.stdin.close()
            with contextlib.suppress(Exception):
                await proc.stdin.wait_closed()
        if proc is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=_CLOSE_TIMEOUT)
            if not self.exit_future.done():
                self.exit_future.set_result(0)
            # wait() above may have timed out with the child still running.
            with contextlib.suppress(ProcessLookupError, RuntimeError):
                proc.terminate()
            with contextlib.suppress(TimeoutError, ProcessLookupError, RuntimeError):
                await asyncio.wait_for(proc.wait(), timeout=_KILL_TIMEOUT)
            with contextlib.suppress(ProcessLookupError, RuntimeError):
                proc.kill()
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._reader_task = None
        self._stderr_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(PiRpcError("pi child closed"))
        self._pending.clear()

    async def _command(self, command: dict[str, Any]) -> dict[str, Any]:
        proc = self._proc
        cmd_id = str(command.get("id", ""))
        if proc is None or proc.stdin is None:
            raise PiRpcError("pi child not started")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[cmd_id] = fut
        try:
            proc.stdin.write(json.dumps(command).encode("utf-8") + b"\n")
            await proc.stdin.drain()
            return await asyncio.wait_for(fut, timeout=_COMMAND_TIMEOUT)
        finally:
            self._pending.pop(cmd_id, None)

    async def _read_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        buf = bytearray()
        try:
            while True:
                chunk = await proc.stdout.read(_READ_CHUNK)
                if not chunk:
                    break
                buf += chunk
                while True:
                    idx = buf.find(b"\n")
                    if idx < 0:
                        break
                    line = bytes(buf[:idx])
                    del buf[: idx + 1]
                    if line.endswith(b"\r"):
                        line = line[:-1]
                    self._dispatch_line(line)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pi RPC stdout reader failed")
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(PiRpcError("pi child closed stdout"))
            self._pending.clear()
            asyncio.ensure_future(self._complete_exit(proc))

    async def _complete_exit(self, proc: PiProcess) -> None:
        if self.exit_future.done():
            return
        with contextlib.suppress(Exception):
            rc = await proc.wait()
            if not self.exit_future.done():
                self.exit_future.set_result(rc)

    def _dispatch_line(self, line: bytes) -> None:
        if not line:
            return
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            logger.warning("skipping undecodable pi RPC record: %r", line[:200])
            return
        if not isinstance(record, dict):
            logger.warning("skipping non-object pi RPC record: %r", record)
            return
        if record.get("type") == "response":
            cmd_id = record.get("id")
            fut = self._pending.get(cmd_id) if isinstance(cmd_id, str) else None
            if fut is not None and not fut.done():
                fut.set_result(record)
            return
        self._emit_event(record)

    def _emit_event(self, record: dict[str, Any]) -> None:
        handler = self._event_handler
        if handler is None:
            return

        async def _run() -> None:
            try:
                await handler(record)
            except Exception:
                logger.exception("agent bridge event handler failed for %r", record.get("type"))

        asyncio.ensure_future(_run())

    @staticmethod
    async def _drain_stderr(proc: PiProcess) -> None:
        stderr = proc.stderr
        assert stderr is not None
        while True:
            chunk = await stderr.read(4096)
            if not chunk:
                return
            logger.debug("pi stderr: %s", chunk.decode("utf-8", "replace").rstrip())


def _extract_assistant_text(message: dict[str, Any]) -> str | None:
    """Pull the text content out of a message_end assistant message."""
    content = message.get("content")
    if isinstance(content, str):
        return content or None
    if not isinstance(content, list):
        return None
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    text = "\n".join(p for p in parts if p)
    return text or None


def _extract_kimi_text(data: bytes) -> str | None:
    """Best-effort text extraction from kimi ``--output-format stream-json`` output."""
    raw = data.decode("utf-8", "replace")
    pieces: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        for key in ("text", "delta", "content", "message"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                pieces.append(value)
                break
    result = "\n".join(pieces).strip() or raw.strip()
    if len(result) > _REVIEW_MAX_CHARS:
        result = result[:_REVIEW_MAX_CHARS] + "…"
    return result or None


def _extract_kimi_resume_id(output: str) -> str | None:
    """Parse the resume token (``session_<uuid>``) from kimi's stdout trailer."""
    for line in output.splitlines():
        match = _KIMI_RESUME_RE.match(line.strip())
        if match:
            return match.group(1)
    return None


def _clean_kimi_output(output: str) -> str:
    """Strip the version banner and resume trailer from kimi ``-p`` stdout."""
    lines = [
        line
        for line in output.splitlines()
        if not _KIMI_RESUME_RE.match(line.strip()) and not _KIMI_VERSION_RE.match(line.strip())
    ]
    return "\n".join(lines).strip()


@dataclass
class _KimiChatSession:
    """Per-chat state for the Kimi CLI backend (L251): one in-flight run."""

    platform_user: str
    running: bool = False
    session_id: str | None = None  # cached; persisted via the chat settings store
    proc: asyncio.subprocess.Process | None = None
    status_message_id: str | None = None


@dataclass
class _ChatSession:
    """Per-chat bridge state: one Pi child plus run bookkeeping."""

    client: PiRpcClient
    platform_user: str
    workspace: Path
    running: bool = False
    broken: bool = False
    closing: bool = False
    status_message_id: str | None = None
    status_text: str = ""
    headline: str = ""
    status_event: asyncio.Event = field(default_factory=asyncio.Event)
    editor_task: asyncio.Task[None] | None = None
    exit_task: asyncio.Task[None] | None = None
    streamed: list[str] = field(default_factory=list)
    last_stream_edit: float = 0.0
    final_text: str | None = None
    run_failed: bool = False
    pre_head: str | None = None
    consecutive_failures: int = 0
    escalation_pending: bool = False
    active_task: str = ""


class AgentBridge:
    """Routes allowlisted Telegram chats to persistent Pi coding-agent children.

    - First message for a chat spawns ``pi --mode rpc`` in a per-chat workspace
      (``<agent_bridge_workspace>/<chat-id>``, git-initialized and seeded with
      the repair-agent AGENTS.md on first use); later messages reuse the child.
    - A message arriving while a run is active is sent as a steering prompt.
    - Status UX: one status message per run, edited on progress; the final
      assistant answer is delivered as a new message.
    - Retry/queue events map to a "queued" status; child exit marks the session
      broken and the next message respawns the child.
    - §4: after ``agent_settled``, if workspace HEAD advanced, a Kimi reviewer
      spawns once (read-only, fire-and-forget). Two consecutive failed runs in a
      chat offer to hand the task to Kimi for execution.
    - L251: a per-chat selectable backend (``pi`` default, ``kimi`` for the Kimi
      Code CLI) resolved from the chat settings store before dispatch. Kimi runs
      are one-shot subprocess invocations resumed via a persisted session id.
    - Repairs: after a successful run, a deploy-request marker in the chat
      workspace triggers the gated deploy pipeline — Kimi must APPROVE the
      repo diff before services restart and health is verified.
    """

    def __init__(
        self,
        adapter: TelegramAdapter,
        config: TelegramConfig,
        *,
        client_factory: Callable[[], PiRpcClient] | None = None,
        head_resolver: HeadResolver | None = None,
        diff_resolver: DiffResolver | None = None,
        kimi_runner: KimiRunner | None = None,
        command_runner: CommandRunner | None = None,
        chat_settings_store: ChatSettingsStore | None = None,
    ) -> None:
        self._adapter = adapter
        self._config = config
        self._client_factory = client_factory or (lambda: PiRpcClient())
        self._workspace_root = Path(os.path.expanduser(config.agent_bridge_workspace))
        self._sessions: dict[str, _ChatSession] = {}
        self._kimi_sessions: dict[str, _KimiChatSession] = {}
        self._closed = False
        self._command_runner = command_runner or _run_command
        self._head_resolver = head_resolver or self._default_head
        self._diff_resolver = diff_resolver or self._default_diff
        self._kimi_runner = kimi_runner or self._run_kimi
        self._chat_settings_store = chat_settings_store

    async def _default_head(self, workspace: Path) -> str | None:
        rc, out = await self._command_runner("git", "-C", str(workspace), "rev-parse", "HEAD")
        head = out.strip()
        return head if rc == 0 and head else None

    async def _default_diff(self, workspace: Path, pre: str, head: str) -> str | None:
        rc, out = await self._command_runner("git", "-C", str(workspace), "diff", f"{pre}..{head}", "--")
        return out if rc == 0 else None

    def _workspace_for(self, platform_user: str) -> Path:
        """Per-chat workspace path (flat layout only when explicitly requested)."""
        if os.environ.get(_FLAT_WORKSPACE_ENV) == "1":
            return self._workspace_root
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", platform_user)
        return self._workspace_root / safe

    async def _ensure_workspace(self, workspace: Path) -> None:
        """Create the chat workspace if needed: git init + seed AGENTS.md once."""
        workspace.mkdir(parents=True, exist_ok=True)
        if not (workspace / ".git").exists():
            await self._command_runner("git", "-C", str(workspace), "init", "-q")
        agents_md = workspace / "AGENTS.md"
        if not agents_md.exists():
            agents_md.write_text(AGENT_WORKSPACE_AGENTS_MD, encoding="utf-8")

    def should_route(self, platform_user: str) -> bool:
        """True when this chat is allowlisted for the coding agent."""
        return self._config.agent_bridge_enabled and platform_user in self._config.agent_bridge_chats

    async def handle(self, platform_user: str, text: str) -> None:
        """Route one incoming chat message to the coding agent."""
        if self._closed:
            logger.debug("bridge closed; dropping message from %s", platform_user)
            return
        if await self._resolve_backend(platform_user) == BACKEND_KIMI:
            await self._handle_kimi(platform_user, text)
            return
        session = self._sessions.get(platform_user)

        if (
            session is not None
            and session.escalation_pending
            and await self._resolve_escalation(session, text)
        ):
            return

        if session is None or session.broken:
            if session is not None:
                await self._drop_session(session)
            try:
                session = await self._spawn_session(platform_user)
            except Exception as e:  # noqa: BLE001 — spawn boundary: report, never crash the bot
                logger.exception("Failed to spawn coding agent for %s", platform_user)
                with contextlib.suppress(Exception):
                    await self._adapter.send_message(
                        platform_user,
                        f"⚠️ could not start the coding agent: {e}",
                    )
                return

        assert session is not None
        if session.running:
            await self._steer(session, text)
            return

        await self._start_run(session, text)

    async def aclose(self) -> None:
        """Terminate all Pi children and stop background tasks."""
        self._closed = True
        sessions = list(self._sessions.values())
        self._sessions.clear()
        kimi_sessions = list(self._kimi_sessions.values())
        self._kimi_sessions.clear()
        for kimi_session in kimi_sessions:
            kimi_session.running = False
            if kimi_session.proc is not None:
                with contextlib.suppress(ProcessLookupError, RuntimeError):
                    kimi_session.proc.kill()
        for session in sessions:
            session.closing = True
            for task in (session.editor_task, session.exit_task):
                if task is not None:
                    task.cancel()
        results = await asyncio.gather(
            *(session.client.aclose() for session in sessions),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("error closing pi child: %s", result)
        for session in sessions:
            for task in (session.editor_task, session.exit_task):
                if task is not None:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def _spawn_session(self, platform_user: str) -> _ChatSession:
        client = self._client_factory()
        workspace = self._workspace_for(platform_user)
        await self._ensure_workspace(workspace)
        session = _ChatSession(client=client, platform_user=platform_user, workspace=workspace)

        async def _handler(record: dict[str, Any], s: _ChatSession = session) -> None:
            await self._on_event(s, record)

        client.set_event_handler(_handler)
        await client.start(
            cwd=str(workspace),
            name=f"tg-{platform_user}",
            env={"PI_SESSION_ID": platform_user},
        )
        session.exit_task = asyncio.create_task(self._watch_exit(session))
        self._sessions[platform_user] = session
        logger.info(
            "spawned pi coding agent for chat %s (workspace=%s)", platform_user, workspace
        )
        return session

    async def _drop_session(self, session: _ChatSession) -> None:
        session.closing = True
        for task in (session.editor_task, session.exit_task):
            if task is not None:
                task.cancel()
        with contextlib.suppress(Exception):
            await session.client.aclose()
        self._sessions.pop(session.platform_user, None)

    async def _watch_exit(self, session: _ChatSession) -> None:
        rc = await session.client.exit_future
        if session.closing or self._closed:
            return
        logger.warning("pi child for chat %s exited (rc=%s)", session.platform_user, rc)
        session.broken = True
        if session.running:
            session.running = False
            if session.editor_task is not None:
                session.editor_task.cancel()
            with contextlib.suppress(Exception):
                await self._adapter.set_typing(session.platform_user, False)
        with contextlib.suppress(Exception):
            await self._adapter.send_message(
                session.platform_user,
                "⚠️ the coding agent exited unexpectedly — I'll restart it on your next message.",
            )

    # ------------------------------------------------------------------
    # L251 Kimi CLI backend (per-chat selectable via /agent)
    # ------------------------------------------------------------------

    async def _resolve_backend(self, platform_user: str) -> str:
        """Resolve the chat's backend: stored override, else pi; no store → pi."""
        store = self._chat_settings_store
        if store is None:
            return BACKEND_PI
        try:
            backend = await store.get_agent_backend("telegram", platform_user)
        except Exception:
            logger.exception("failed to read agent backend for chat %s", platform_user)
            return BACKEND_PI
        if backend in (BACKEND_PI, BACKEND_KIMI):
            return backend
        if backend:
            logger.warning(
                "unknown agent backend %r for chat %s; falling back to pi", backend, platform_user
            )
        return BACKEND_PI

    async def _handle_kimi(self, platform_user: str, text: str) -> None:
        if not self._config.agent_bridge_kimi_workdir:
            with contextlib.suppress(Exception):
                await self._adapter.send_message(
                    platform_user,
                    "⚠️ the Kimi backend is not configured (no workdir set) — staying on pi.",
                )
            return
        session = self._kimi_sessions.get(platform_user)
        if session is None:
            session = _KimiChatSession(platform_user=platform_user)
            store = self._chat_settings_store
            if store is not None:
                with contextlib.suppress(Exception):
                    session.session_id = await store.get_kimi_session_id("telegram", platform_user)
            self._kimi_sessions[platform_user] = session
        if session.running:
            with contextlib.suppress(Exception):
                await self._adapter.send_message(
                    platform_user,
                    "⏳ still working on your previous message — one Kimi run at a time per chat.",
                )
            return
        await self._run_kimi_chat(session, text)

    async def _run_kimi_chat(self, session: _KimiChatSession, text: str) -> None:
        """Drive one kimi run end-to-end: status, subprocess, delivery."""
        user = session.platform_user
        session.running = True
        try:
            session.status_message_id = await self._adapter.send_message(user, "🤖 working… (kimi)")
        except Exception as e:  # noqa: BLE001 — status UX is best effort
            logger.warning("failed to send status message to %s: %s", user, e)
            session.status_message_id = None
        with contextlib.suppress(Exception):
            await self._adapter.set_typing(user, True)
        reply: str | None = None
        error: str | None = None
        try:
            reply, session_id, error = await self._run_kimi_turn(session, text)
        except Exception:  # noqa: BLE001 — report, never crash the bot
            logger.exception("kimi run crashed for chat %s", user)
            error = "⚠️ the Kimi run crashed unexpectedly — check the logs and try again."
        finally:
            session.running = False
            with contextlib.suppress(Exception):
                await self._adapter.set_typing(user, False)
        store = self._chat_settings_store
        if session_id:
            session.session_id = session_id
            if store is not None:
                with contextlib.suppress(Exception):
                    await store.set_kimi_session_id("telegram", user, session_id)
        if session.status_message_id is not None:
            headline = "✅ done" if reply is not None and error is None else (error or "⚠️ run failed")
            with contextlib.suppress(Exception):
                await self._adapter.edit_message(user, session.status_message_id, headline)
        if reply is not None:
            with contextlib.suppress(Exception):
                await self._adapter.send_message(user, reply)
        elif error is not None:
            with contextlib.suppress(Exception):
                await self._adapter.send_message(user, error)

    async def _run_kimi_turn(
        self, session: _KimiChatSession, text: str
    ) -> tuple[str | None, str | None, str | None]:
        """Run one ``kimi -p`` invocation. Returns (reply, session_id, error).

        The first run starts a fresh kimi session; later turns pass the persisted
        session id via ``-S`` so the whole chat shares one kimi session. Errors
        returned here are sanitized for chat delivery (no paths or stack traces).
        """
        workdir = os.path.expanduser(self._config.agent_bridge_kimi_workdir)
        command = [self._config.agent_bridge_kimi_bin]
        if session.session_id:
            command.extend(["-S", session.session_id])
        command.extend(["-p", text])
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            logger.warning("failed to spawn kimi for chat %s: %s", session.platform_user, e)
            return None, None, "⚠️ could not start the Kimi CLI (is it installed and on PATH?)."
        session.proc = proc
        try:
            try:
                stdout, _stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._config.agent_bridge_kimi_timeout_seconds
                )
            except TimeoutError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                logger.warning("kimi run for chat %s timed out", session.platform_user)
                return (
                    None,
                    None,
                    f"⚠️ the Kimi run timed out after "
                    f"{int(self._config.agent_bridge_kimi_timeout_seconds)}s — try again, "
                    "or switch back with /agent pi.",
                )
        finally:
            session.proc = None
        output = stdout.decode("utf-8", "replace")
        session_id = _extract_kimi_resume_id(output)
        rc = proc.returncode or 0
        if rc != 0:
            logger.warning("kimi exited %s for chat %s", rc, session.platform_user)
            return None, session_id, f"⚠️ Kimi exited with code {rc}; no reply was produced."
        reply = _clean_kimi_output(output)
        if not reply:
            return None, session_id, "⚠️ Kimi finished without producing any output."
        return reply, session_id, None

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    async def _start_run(self, session: _ChatSession, text: str) -> None:
        session.active_task = text
        session.running = True
        session.run_failed = False
        session.final_text = None
        session.streamed.clear()
        session.last_stream_edit = 0.0
        session.pre_head = await self._head_resolver(session.workspace)
        try:
            session.status_message_id = await self._adapter.send_message(
                session.platform_user, "🤖 working…"
            )
        except Exception as e:  # noqa: BLE001 — status UX is best effort
            logger.warning("failed to send status message to %s: %s", session.platform_user, e)
            session.status_message_id = None
        session.headline = "🤖 working…"
        session.status_text = session.headline
        session.editor_task = asyncio.create_task(self._status_editor(session))
        with contextlib.suppress(Exception):
            await self._adapter.set_typing(session.platform_user, True)
        try:
            response = await session.client.prompt(text)
        except PiRpcError as e:
            if "already processing" not in str(e).lower():
                logger.warning("prompt rejected for chat %s: %s", session.platform_user, e)
                await self._end_run(session, failed=True, note=str(e))
                return
            # Race: the child was still processing (e.g. trailing retries after
            # agent_end) but session.running was already False. Re-queue as
            # steering instead of dropping the user's message (Pi 1.3.0 rejects
            # plain prompts mid-stream: "Specify streamingBehavior").
            logger.info("chat %s message arrived mid-run; re-queuing as steer", session.platform_user)
            try:
                response = await session.client.prompt(text, steer=True)
            except PiRpcError as e2:
                logger.warning("steer rejected for chat %s: %s", session.platform_user, e2)
                await self._end_run(session, failed=True, note=str(e2))
                return
        disposition = (response.get("data") or {}).get("disposition")
        if disposition == "handled":
            # An extension command consumed the prompt: no run will start.
            await self._end_run(session, failed=False, note="command handled; no run started")

    async def _steer(self, session: _ChatSession, text: str) -> None:
        try:
            await session.client.prompt(text, steer=True)
        except PiRpcError as e:
            logger.warning("steering message rejected for chat %s: %s", session.platform_user, e)
            with contextlib.suppress(Exception):
                await self._adapter.send_message(
                    session.platform_user, f"⚠️ could not queue your follow-up: {e}"
                )
            return
        self._set_status(session, "🛠 received your follow-up — steering the run")

    async def _on_event(self, session: _ChatSession, record: dict[str, Any]) -> None:
        rtype = record.get("type")
        if rtype == "extension_ui_request":
            await self._on_extension_ui(session, record)
        elif rtype == "agent_start":
            self._set_status(session, "🤖 working…")
        elif rtype == "message_update":
            event = record.get("assistantMessageEvent")
            if not isinstance(event, dict):
                return
            etype = event.get("type")
            if etype == "text_delta":
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    session.streamed.append(delta)
                    self._refresh_stream_status(session)
            elif etype == "error":
                session.run_failed = True
        elif rtype == "tool_execution_start":
            tool = record.get("toolName")
            self._set_status(session, f"🔧 tool: {tool}" if isinstance(tool, str) else "🔧 running a tool")
        elif rtype == "auto_retry_start":
            attempt = record.get("attempt")
            max_attempts = record.get("maxAttempts")
            self._set_status(
                session,
                f"⏳ queued behind another task — retrying (attempt {attempt}/{max_attempts})",
            )
        elif rtype == "auto_retry_end":
            if not record.get("success", True):
                session.run_failed = True
                self._set_status(
                    session, f"⚠️ model call failed: {record.get('finalError', 'unknown error')}"
                )
        elif rtype == "summarization_retry_scheduled":
            self._set_status(session, "⏳ compacting context — retrying…")
        elif rtype == "queue_update":
            steering = record.get("steering") or []
            follow_up = record.get("followUp") or []
            if steering or follow_up:
                self._set_status(
                    session,
                    f"📥 queued: {len(steering)} steering / {len(follow_up)} follow-up message(s)",
                )
        elif rtype == "message_end":
            message = record.get("message")
            if isinstance(message, dict) and message.get("role") == "assistant":
                text = _extract_assistant_text(message)
                if text is not None:
                    session.final_text = text
        elif rtype == "agent_settled":
            aborted = bool(record.get("aborted"))
            await self._end_run(session, failed=session.run_failed or aborted, aborted=aborted)

    async def _on_extension_ui(self, session: _ChatSession, record: dict[str, Any]) -> None:
        """Surface Pi extension UI notifications (e.g. small-coder interventions).

        small-coder's turn-cap aborts with ``ctx.ui.notify("harness intervention:
        turn limit reached …")`` — without this, the bridge showed a bare
        "⚠️ run aborted" with no reason. Only fire-and-forget ``notify`` records
        are handled; interactive requests (confirm/custom) are ignored (v1).
        """
        if record.get("method") != "notify":
            return
        message = record.get("message")
        if not isinstance(message, str) or not message.strip():
            return
        logger.info("pi extension notify for chat %s: %s", session.platform_user, message)
        text = f"ℹ️ {message.strip()}"
        if session.running:
            # Transient: the next progress event overwrites the status headline.
            self._set_status(session, text)
        else:
            with contextlib.suppress(Exception):
                await self._adapter.send_message(session.platform_user, text)

    async def _end_run(
        self,
        session: _ChatSession,
        *,
        failed: bool,
        aborted: bool = False,
        note: str | None = None,
    ) -> None:
        if not session.running:
            return
        session.running = False
        if session.editor_task is not None:
            session.editor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.editor_task
            session.editor_task = None
        with contextlib.suppress(Exception):
            await self._adapter.set_typing(session.platform_user, False)

        if aborted:
            headline = "⚠️ run aborted"
        elif failed:
            headline = f"⚠️ run failed{': ' + note if note else ''}"
        else:
            headline = "✅ done"
        if session.status_message_id is not None:
            with contextlib.suppress(Exception):
                # On success the full answer is posted as its own message right
                # below — keeping the streamed tail here reads as a duplicate.
                # On failure/aborted the tail is the only record of what happened.
                status_text = headline if not failed and not aborted else self._compose_status(session, headline)
                await self._adapter.edit_message(
                    session.platform_user,
                    session.status_message_id,
                    status_text,
                )
        if session.final_text and not aborted:
            with contextlib.suppress(Exception):
                await self._adapter.send_message(session.platform_user, session.final_text)

        if failed:
            session.consecutive_failures += 1
            if session.consecutive_failures >= 2 and not session.escalation_pending:
                session.escalation_pending = True
                session.consecutive_failures = 0
                with contextlib.suppress(Exception):
                    await self._adapter.send_message(
                        session.platform_user,
                        "Two runs in a row failed in this chat. Hand this task to Kimi "
                        "instead? (yes/no)",
                    )
        else:
            session.consecutive_failures = 0

        # §4 reviewer: fire-and-forget, gated on HEAD advancing during the run.
        self._maybe_review(session)
        # Autonomous repair: a successful run may have left a deploy request.
        if not failed and not aborted:
            self._maybe_deploy(session)

    # ------------------------------------------------------------------
    # Autonomous repair deploy pipeline
    # (marker -> dirty-tree gate -> Kimi gate -> restart -> verify -> rollback)
    # ------------------------------------------------------------------

    def _maybe_deploy(self, session: _ChatSession) -> None:
        if self._deploy_request_path(session).exists():
            asyncio.ensure_future(self._deploy_task(session))

    def _deploy_request_path(self, session: _ChatSession) -> Path:
        return session.workspace / _DEPLOY_REQUEST_REL

    def _validate_deploy_request(self, req: Any) -> str | None:
        """Return an error string, or None when the request is well-formed."""
        if not isinstance(req, dict):
            return "request is not a JSON object"
        repo = req.get("repo")
        if isinstance(repo, str):
            # Accept $HOME/~ forms written by repair agents; compare resolved.
            repo = os.path.expandvars(os.path.expanduser(repo))
            req["repo"] = repo
        if not isinstance(repo, str) or repo not in _DEPLOY_ALLOWED_REPOS:
            return f"repo must be one of {_DEPLOY_ALLOWED_REPOS}"
        for key in ("base_ref", "summary"):
            value = req.get(key)
            if not isinstance(value, str) or not value.strip():
                return f"{key} must be a non-empty string"
        commits = req.get("commits")
        if not isinstance(commits, list) or not all(isinstance(c, str) and c for c in commits):
            return "commits must be a list of commit shas"
        services = req.get("services", [])
        if not isinstance(services, list) or not all(isinstance(s, str) for s in services):
            return "services must be a list of unit names"
        for svc in services:
            if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", svc):
                return f"invalid service name {svc!r}"
            if svc == "hestia-tg-agent":
                return "refusing to restart hestia-tg-agent (that is this bot)"
        health_url = req.get("health_url")
        if health_url is not None and not isinstance(health_url, str):
            return "health_url must be a string or omitted"
        return None

    async def _notify(self, user: str, text: str) -> None:
        with contextlib.suppress(Exception):
            await self._adapter.send_message(user, text)

    async def _deploy_task(self, session: _ChatSession) -> None:
        """Review, deploy, and verify a repair requested by the agent.

        Runs only after a successful run that left a deploy-request marker in
        the chat workspace. Kimi (read-only reviewer) must APPROVE the repo
        diff before any service is restarted; a rejected or unavailable
        review means no deploy. Uncommitted changes in the target repo block
        deployment — the tree must belong to the committed fix alone.
        """
        user = session.platform_user
        path = self._deploy_request_path(session)

        async def _finish(message: str) -> None:
            with contextlib.suppress(Exception):
                path.unlink()
            if message:
                await self._notify(user, message)

        try:
            try:
                req = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                await _finish(f"⚠️ deploy request unreadable ({exc}); not deploying.")
                return
            error = self._validate_deploy_request(req)
            if error:
                await _finish(f"⚠️ deploy request invalid: {error}. Not deploying.")
                return
            if os.environ.get(_DEPLOY_ENV_FLAG) != "1":
                await _finish(
                    f"🔒 Fix committed, but auto-deploy is disabled "
                    f"(set {_DEPLOY_ENV_FLAG}=1 for hestia-tg-agent); not deploying. "
                    f"Summary: {req['summary']}"
                )
                return

            repo = req["repo"]
            summary = req["summary"].strip()

            rc, status = await self._command_runner("git", "-C", repo, "status", "--porcelain")
            if rc != 0:
                await _finish(f"⚠️ cannot inspect {repo} (git status failed); not deploying.")
                return
            if status.strip():
                await _finish(
                    f"⚠️ {summary}\nNot deploying: {repo} has uncommitted changes. "
                    "The tree must contain only the committed repair. Left as-is."
                )
                return

            rc, diff = await self._command_runner(
                "git", "-C", repo, "diff", f"{req['base_ref']}..HEAD", "--"
            )
            if rc != 0 or not diff.strip():
                await _finish(
                    f"⚠️ could not produce a diff from {req['base_ref']} in {repo}; not deploying."
                )
                return
            if len(diff) > _DIFF_MAX_CHARS:
                diff = diff[:_DIFF_MAX_CHARS] + "\n… (diff truncated)"
            review_prompt = _REPAIR_REVIEW_INSTRUCTIONS.format(
                repo=repo, summary=summary, diff=diff
            )
            verdict = await self._kimi_runner(review_prompt, True)
            if verdict is None:
                await _finish(
                    f"⚠️ {summary}\nKimi review unavailable; safeguard says do not deploy "
                    "unaudited. The fix is committed — restart the service to apply, "
                    "or ask me to retry the deploy."
                )
                return
            if not _verdict_is_approval(verdict):
                await _finish(f"📝 {summary}\nKimi requested changes — not deployed.\n\n{verdict}")
                return

            healthy = await self._restart_and_verify(req["services"], req.get("health_url"))
            if healthy:
                await _finish(
                    f"✅ {summary}\nKimi review: APPROVED. Deployed and verified healthy."
                )
                return
            rolled_back = await self._rollback(req)
            if rolled_back:
                await _finish(
                    f"⚠️ {summary}\nKimi review: APPROVED, but the deploy failed health "
                    "checks — rolled the commits back and restarted. Still unhealthy; "
                    "Dylan should take a look."
                )
            else:
                await _finish(
                    f"⚠️ {summary}\nKimi review: APPROVED, but the deploy failed health "
                    "checks and the rollback did not complete cleanly. Dylan should look."
                )
        except Exception:
            logger.exception("deploy pipeline failed for chat %s", user)
            await _finish("⚠️ the deploy pipeline crashed; the fix is committed but not deployed.")

    async def _restart_and_verify(
        self, services: list[str], health_url: str | None
    ) -> bool:
        """Restart services, then poll until all are active (and health URL
        responds, when given). True = healthy."""
        for svc in services:
            rc, out = await self._command_runner("systemctl", "--user", "restart", svc)
            if rc != 0:
                logger.warning("systemctl restart %s failed: %s", svc, out.strip()[-300:])
                return False
        deadline = time.monotonic() + _DEPLOY_HEALTH_TIMEOUT_SECONDS
        while True:
            await asyncio.sleep(_DEPLOY_HEALTH_INTERVAL_SECONDS)
            ok = True
            for svc in services:
                rc, out = await self._command_runner("systemctl", "--user", "is-active", svc)
                if rc != 0 or out.strip() != "active":
                    ok = False
            if ok and health_url:
                rc, _ = await self._command_runner(
                    "curl", "-sf", "-o", "/dev/null", "-m", "5", health_url
                )
                ok = rc == 0
            if ok:
                return True
            if time.monotonic() >= deadline:
                return False

    async def _rollback(self, req: dict[str, Any]) -> bool:
        """git revert the repair commits and restart services. True when the
        revert landed and every service came back active."""
        repo: str = req["repo"]
        rc, _ = await self._command_runner(
            "git", "-C", repo, "revert", "--no-edit", *req["commits"]
        )
        if rc != 0:
            return False
        return await self._restart_and_verify(req["services"], req.get("health_url"))

    # ------------------------------------------------------------------
    # Status UX
    # ------------------------------------------------------------------

    def _compose_status(self, session: _ChatSession, headline: str) -> str:
        tail = "".join(session.streamed)
        if len(tail) > _STREAM_TAIL_CHARS:
            tail = "…" + tail[-_STREAM_TAIL_CHARS:]
        return f"{headline}\n\n{tail}" if tail else headline

    def _set_status(self, session: _ChatSession, headline: str) -> None:
        session.headline = headline
        session.status_text = self._compose_status(session, headline)
        session.status_event.set()

    def _refresh_stream_status(self, session: _ChatSession) -> None:
        now = time.monotonic()
        if now - session.last_stream_edit < _STATUS_EDIT_INTERVAL:
            return
        session.last_stream_edit = now
        session.status_text = self._compose_status(session, session.headline)
        session.status_event.set()

    async def _status_editor(self, session: _ChatSession) -> None:
        interval = max(_STATUS_EDIT_INTERVAL, self._config.rate_limit_edits_seconds)
        try:
            while True:
                await session.status_event.wait()
                session.status_event.clear()
                if session.status_message_id is None:
                    continue
                try:
                    await self._adapter.edit_message(
                        session.platform_user, session.status_message_id, session.status_text
                    )
                except Exception as e:  # noqa: BLE001 — status UX is best effort
                    logger.warning("status edit failed for chat %s: %s", session.platform_user, e)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    # §4 Kimi reviewer loop
    # ------------------------------------------------------------------

    def _maybe_review(self, session: _ChatSession) -> None:
        if not session.pre_head:
            return
        # Fire-and-forget: the executor never blocks on the reviewer's verdict.
        asyncio.ensure_future(self._review_task(session))

    async def _review_task(self, session: _ChatSession) -> None:
        user = session.platform_user
        pre_head = session.pre_head
        if not pre_head:
            return
        try:
            head = await self._head_resolver(session.workspace)
            if head is None or head == pre_head:
                return
            diff = await self._diff_resolver(session.workspace, pre_head, head)
            if not diff:
                return
            if len(diff) > _DIFF_MAX_CHARS:
                diff = diff[:_DIFF_MAX_CHARS] + "\n… (diff truncated)"
            prompt = _REVIEW_INSTRUCTIONS.format(workspace=str(session.workspace), diff=diff)
            verdict = await self._kimi_runner(prompt, True)
            if verdict:
                with contextlib.suppress(Exception):
                    await self._adapter.send_message(user, f"📝 Kimi review:\n\n{verdict}")
        except Exception:
            # Reviewer failure must never crash the bridge.
            logger.exception("Kimi review failed for chat %s", user)

    async def _resolve_escalation(self, session: _ChatSession, text: str) -> bool:
        reply = text.strip().lower()
        if reply in _YES_REPLIES:
            session.escalation_pending = False
            task = session.active_task
            with contextlib.suppress(Exception):
                await self._adapter.send_message(session.platform_user, "🤝 handing the task to Kimi…")
            asyncio.ensure_future(self._kimi_exec(session, task))
            return True
        if reply in _NO_REPLIES:
            session.escalation_pending = False
            with contextlib.suppress(Exception):
                await self._adapter.send_message(session.platform_user, "OK — continuing with the local agent.")
            return True
        # Unclear reply: drop the offer and let the message flow to the agent.
        session.escalation_pending = False
        return False

    async def _kimi_exec(self, session: _ChatSession, task: str) -> None:
        user = session.platform_user
        try:
            prompt = _EXEC_INSTRUCTIONS.format(workspace=str(session.workspace), task=task)
            result = await self._kimi_runner(prompt, False)
            if result:
                with contextlib.suppress(Exception):
                    await self._adapter.send_message(user, f"🤝 Kimi:\n\n{result}")
            else:
                with contextlib.suppress(Exception):
                    await self._adapter.send_message(
                        user, "⚠️ Kimi run failed — check the logs for details."
                    )
        except Exception:
            logger.exception("Kimi execution failed for chat %s", user)

    async def _run_kimi(self, prompt: str, plan: bool) -> str | None:
        """Spawn kimi (2.2.0, on PATH); None on spawn failure or nonzero exit.

        kimi 2.2.0 rejects ``--prompt`` combined with ``--plan``, and ``--session``
        only resumes EXISTING sessions (no non-interactive create). So the
        read-only reviewer is enforced differently: a custom agent file with a
        Read/Grep/Glob allowlist (no Bash/Edit/Write) passed via ``--agent-file``
        — kimi re-checks the allowlist before every tool execution. Both paths
        run sessionless; each invocation is self-contained.
        """
        command = ["kimi", "-p", prompt, "--output-format", "stream-json"]
        if plan:
            agent_file = Path(
                os.environ.get("TG_REVIEWER_AGENT_FILE", _DEFAULT_REVIEWER_AGENT)
            ).expanduser()
            if not agent_file.exists():
                logger.warning(
                    "reviewer agent file %s missing; skipping review (refusing to "
                    "run a writable reviewer)",
                    agent_file,
                )
                return None
            command.extend(["--agent-file", str(agent_file)])
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_KIMI_TIMEOUT)
            except TimeoutError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                logger.warning("kimi timed out after %ss", _KIMI_TIMEOUT)
                return None
        except OSError as e:
            logger.warning("failed to spawn kimi: %s", e)
            return None
        if proc.returncode != 0:
            logger.warning(
                "kimi exited %s: %s",
                proc.returncode,
                stderr.decode("utf-8", "replace")[-500:] if stderr else "",
            )
            return None
        return _extract_kimi_text(stdout)
