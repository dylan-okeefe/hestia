"""Application bootstrap and context for Hestia CLI."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import click

from hestia.artifacts.store import ArtifactStore
from hestia.config import HestiaConfig
from hestia.context.builder import ContextBuilder
from hestia.context.compressor import InferenceHistoryCompressor
from hestia.core.inference import InferenceClient
from hestia.core.types import Session
from hestia.email.adapter import EmailAdapter
from hestia.identity import IdentityCompiler
from hestia.inference import SlotManager
from hestia.memory import MemoryEpochCompiler, MemoryStore
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.orchestrator import Orchestrator
from hestia.persistence.db import Database
from hestia.persistence.failure_store import FailureStore
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.persistence.skill_store import SkillStore
from hestia.persistence.trace_store import TraceStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.scheduler import ReflectionScheduler
from hestia.reflection.store import ProposalStore
from hestia.security import InjectionScanner
from hestia.skills.index import SkillIndexBuilder
from hestia.style.builder import StyleProfileBuilder
from hestia.style.scheduler import StyleScheduler
from hestia.style.store import StyleProfileStore
from hestia.tools.builtin import (
    current_time,
    http_get,
    make_delegate_task_tool,
    make_delete_memory_tool,
    make_email_search_and_read_tool,
    make_email_tools,
    make_list_dir_tool,
    make_list_memories_tool,
    make_read_artifact_tool,
    make_read_file_tool,
    make_save_memory_tool,
    make_search_memory_tool,
    make_web_search_tool,
    make_write_file_tool,
    terminal,
)
from hestia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_CALIBRATION_PATH = Path("docs/calibration.json")


def _make_policy(cfg: HestiaConfig) -> DefaultPolicyEngine:
    """Build the policy engine from config."""
    return DefaultPolicyEngine(
        ctx_window=cfg.inference.context_length,
        default_reasoning_budget=cfg.inference.default_reasoning_budget,
        trust=cfg.trust,
        config=cfg.policy,
    )


class CliResponseHandler:
    """Handles responses from the orchestrator in CLI mode."""

    def __init__(self, verbose: bool = False):
        """Initialize with verbosity flag."""
        self.verbose = verbose

    async def __call__(self, response: str) -> None:
        """Print response to stdout."""
        click.echo(f"\nAssistant: {response}\n")


class CliConfirmHandler:
    """Handles tool confirmation in CLI mode."""

    async def __call__(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Prompt user for confirmation."""
        click.echo(f"\nTool call requested: {tool_name}")
        click.echo(f"Arguments: {arguments}")
        return click.confirm("Execute?", default=True)


async def _compile_and_set_memory_epoch(
    app: CliAppContext,
    session: Session,
) -> bool:
    """Compile memory epoch for the session and set it in context builder.

    Args:
        app: The CLI app context
        session: The current session

    Returns:
        True if an epoch was compiled and set, False otherwise
    """
    if app.epoch_compiler is None:
        return False

    epoch = await app.epoch_compiler.compile(session)
    if epoch.memory_count > 0:
        app.context_builder.set_memory_epoch_prefix(epoch.compiled_text)
        return True
    return False


async def _handle_meta_command(
    cmd: str,
    session: Session,
    session_store: SessionStore,
    app: CliAppContext | None = None,
) -> tuple[bool, Session]:
    """Handle a /meta command. Returns (should_exit, possibly_new_session)."""
    cmd = cmd.strip().lower()

    if cmd in ("/quit", "/exit"):
        return True, session

    if cmd == "/help":
        click.echo("Meta-commands:")
        click.echo("  /quit, /exit     Exit the REPL")
        click.echo("  /reset           Start a new session")
        click.echo("  /history         Print the current session message history")
        click.echo("  /session         Print the current session metadata")
        click.echo("  /refresh         Refresh the memory epoch")
        click.echo("  /help            Show this help")
        return False, session

    if cmd == "/session":
        click.echo(f"Session ID: {session.id}")
        click.echo(f"Platform: {session.platform}")
        click.echo(f"Platform User: {session.platform_user}")
        click.echo(f"State: {session.state.value}")
        click.echo(f"Temperature: {session.temperature.value}")
        click.echo(f"Started: {session.started_at}")
        return False, session

    if cmd == "/history":
        messages = await session_store.get_messages(session.id)
        if not messages:
            click.echo("(empty)")
        else:
            for m in messages:
                role = m.role
                content = (m.content or "")[:200]
                click.echo(f"  [{role}] {content}")
        return False, session

    if cmd == "/reset":
        new_session = await session_store.create_session(
            platform=session.platform,
            platform_user=session.platform_user,
            archive_previous=session,
        )
        click.echo(f"New session: {new_session.id}")
        # Refresh memory epoch for new session
        if app is not None:
            compiled = await _compile_and_set_memory_epoch(app, new_session)
            if compiled:
                click.echo("Memory epoch refreshed.")
        return False, new_session

    if cmd == "/refresh":
        if app is not None:
            compiled = await _compile_and_set_memory_epoch(app, session)
            if compiled:
                click.echo("Memory epoch refreshed.")
            else:
                click.echo("No memories to include in epoch.")
        else:
            click.echo("Cannot refresh: app context not available.")
        return False, session

    click.echo(f"Unknown command: {cmd}. Type /help for a list.")
    return False, session


def _require_scheduler_store(app: CliAppContext) -> SchedulerStore:
    """Return the scheduler store or raise a clear error."""
    if app.scheduler_store is None:
        raise click.UsageError(
            "Scheduler is not configured. Set `scheduler.enabled = True` in your config."
        )
    return app.scheduler_store


class CliAppContext:
    """Typed application context shared across CLI commands."""

    def __init__(
        self,
        config: HestiaConfig,
        db: Database,
        session_store: SessionStore,
        tool_registry: ToolRegistry,
        policy: DefaultPolicyEngine,
        memory_store: MemoryStore,
        failure_store: FailureStore,
        trace_store: TraceStore,
        artifact_store: ArtifactStore,
        scheduler_store: SchedulerStore | None = None,
        skill_store: SkillStore | None = None,
        proposal_store: ProposalStore | None = None,
        style_store: StyleProfileStore | None = None,
        style_builder: StyleProfileBuilder | None = None,
        epoch_compiler: MemoryEpochCompiler | None = None,
        skill_index_builder: SkillIndexBuilder | None = None,
        verbose: bool = False,
        confirm_callback: Any = None,
        calibration_path: Path | None = None,
        compiled_identity: str | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.session_store = session_store
        self.tool_registry = tool_registry
        self.policy = policy
        self.memory_store = memory_store
        self.failure_store = failure_store
        self.trace_store = trace_store
        self.artifact_store = artifact_store
        self.scheduler_store = scheduler_store
        self.skill_store = skill_store
        self.proposal_store = proposal_store
        self.style_store = style_store
        self.style_builder = style_builder
        self.epoch_compiler = epoch_compiler
        self.skill_index_builder = skill_index_builder
        self.verbose = verbose
        self.confirm_callback = confirm_callback
        self._calibration_path = calibration_path
        self._compiled_identity = compiled_identity
        self._inference: InferenceClient | None = None
        self._context_builder: ContextBuilder | None = None
        self._slot_manager: SlotManager | None = None
        self._reflection_scheduler: ReflectionScheduler | None = None
        self._style_scheduler: StyleScheduler | None = None
        self._handoff_summarizer: SessionHandoffSummarizer | None = None
        self._bootstrapped = False

    @property
    def inference(self) -> InferenceClient:
        """Lazy inference client — created on first access."""
        if self._inference is None:
            model_name = self.config.inference.model_name or "dummy"
            self._inference = InferenceClient(self.config.inference.base_url, model_name)
        return self._inference

    @property
    def context_builder(self) -> ContextBuilder:
        """Lazy context builder — created on first access."""
        if self._context_builder is None:
            path = self._calibration_path or DEFAULT_CALIBRATION_PATH
            cb = ContextBuilder.from_calibration_file(self.inference, self.policy, path)
            if self._compiled_identity:
                cb.set_identity_prefix(self._compiled_identity)
            if self.config.compression.enabled:
                cb.enable_compression(
                    InferenceHistoryCompressor(
                        self.inference, max_chars=self.config.compression.max_chars
                    )
                )
            self._context_builder = cb
        return self._context_builder

    @property
    def slot_manager(self) -> SlotManager:
        """Lazy slot manager — created on first access."""
        if self._slot_manager is None:
            self._slot_manager = SlotManager(
                inference=self.inference,
                session_store=self.session_store,
                slot_dir=self.config.slots.slot_dir,
                pool_size=self.config.slots.pool_size,
            )
        return self._slot_manager

    @property
    def reflection_scheduler(self) -> ReflectionScheduler | None:
        """Lazy reflection scheduler — created on first access.

        Construction is unconditional so callers can read status/failure
        history even when the scheduler is not auto-started by daemons.
        Whether the scheduler actually ticks is governed by
        ``config.reflection.enabled`` checks at the start sites.
        """
        if self._reflection_scheduler is None:
            if self.proposal_store is None:
                return None
            runner = ReflectionRunner(
                config=self.config.reflection,
                inference=self.inference,
                trace_store=self.trace_store,
                proposal_store=self.proposal_store,
            )
            sched = ReflectionScheduler(
                config=self.config.reflection,
                runner=runner,
                session_store=self.session_store,
            )
            runner._on_failure = sched._record_failure
            self._reflection_scheduler = sched
        return self._reflection_scheduler

    @property
    def style_scheduler(self) -> StyleScheduler | None:
        """Lazy style scheduler — created on first access if builder is available."""
        if self._style_scheduler is None and self.style_builder is not None:
            self._style_scheduler = StyleScheduler(
                config=self.config.style,
                builder=self.style_builder,
                session_store=self.session_store,
            )
        return self._style_scheduler

    @property
    def handoff_summarizer(self) -> SessionHandoffSummarizer | None:
        """Lazy handoff summarizer — created on first access if enabled."""
        if self._handoff_summarizer is None and self.config.handoff.enabled:
            self._handoff_summarizer = SessionHandoffSummarizer(
                inference=self.inference,
                memory_store=self.memory_store,
                max_chars=self.config.handoff.max_chars,
                min_messages=self.config.handoff.min_messages,
            )
        return self._handoff_summarizer

    async def bootstrap_db(self) -> None:
        """Connect to database and create tables. Idempotent."""
        if self._bootstrapped:
            return
        await self.db.connect()
        await self.db.create_tables()
        await self.memory_store.create_table()
        await self.failure_store.create_table()
        await self.trace_store.create_table()
        if self.skill_store is not None:
            await self.skill_store.create_table()
        if self.proposal_store is not None:
            await self.proposal_store.create_table()
        if self.style_store is not None:
            await self.style_store.create_table()
        self._bootstrapped = True

    def make_injection_scanner(self) -> InjectionScanner:
        """Create an InjectionScanner from config."""
        return InjectionScanner(
            enabled=self.config.security.injection_scanner_enabled,
            entropy_threshold=self.config.security.injection_entropy_threshold,
            skip_filters_for_structured=self.config.security.injection_skip_filters_for_structured,
        )

    def make_orchestrator(self) -> Orchestrator:
        """Create an Orchestrator with the current app context."""
        return Orchestrator(
            inference=self.inference,
            session_store=self.session_store,
            context_builder=self.context_builder,
            tool_registry=self.tool_registry,
            policy=self.policy,
            confirm_callback=self.confirm_callback,
            max_iterations=self.config.max_iterations,
            slot_manager=self.slot_manager,
            failure_store=self.failure_store,
            trace_store=self.trace_store,
            handoff_summarizer=self.handoff_summarizer,
            injection_scanner=self.make_injection_scanner(),
            proposal_store=self.proposal_store,
            style_store=self.style_store,
            style_config=self.config.style,
        )


def make_app(cfg: HestiaConfig) -> CliAppContext:
    """Build subsystems from config and return typed app context."""
    db = Database(cfg.storage.database_url)
    artifact_store = ArtifactStore(cfg.storage.artifacts_dir)
    session_store = SessionStore(db)
    policy = _make_policy(cfg)

    # Honor environment overrides for personality / calibration paths
    env_soul = os.environ.get("HESTIA_SOUL_PATH")
    if env_soul:
        cfg.identity.soul_path = Path(env_soul)
    env_calibration = os.environ.get("HESTIA_CALIBRATION_PATH")
    calibration_path = Path(env_calibration) if env_calibration else DEFAULT_CALIBRATION_PATH

    # Compile identity from SOUL.md when present
    identity_compiler = IdentityCompiler(cfg.identity)
    compiled_identity = identity_compiler.get_compiled_text()

    soul_path = cfg.identity.soul_path
    if soul_path is not None and not soul_path.exists():
        click.echo(
            click.style(
                f"Warning: personality file not found at {soul_path}", fg="yellow"
            ),
            err=True,
        )
        logger.warning("SOUL.md not found at %s", soul_path)

    if not calibration_path.exists():
        click.echo(
            click.style(
                f"Warning: calibration file not found at {calibration_path} — using defaults",
                fg="yellow",
            ),
            err=True,
        )
        logger.warning("Calibration file not found at %s", calibration_path)

    # Memory store for long-term memory
    memory_store = MemoryStore(db)

    # Tool registry with built-in tools
    tool_registry = ToolRegistry(artifact_store)
    tool_registry.register(current_time)
    tool_registry.register(http_get)
    tool_registry.register(make_list_dir_tool(cfg.storage.allowed_roots))
    tool_registry.register(terminal)

    # Register file tools with path sandboxing
    tool_registry.register(make_read_file_tool(cfg.storage.allowed_roots))
    tool_registry.register(make_write_file_tool(cfg.storage.allowed_roots))

    # Register memory tools (bound to the memory store instance)
    tool_registry.register(make_search_memory_tool(memory_store))
    tool_registry.register(make_save_memory_tool(memory_store))
    tool_registry.register(make_list_memories_tool(memory_store))
    tool_registry.register(make_delete_memory_tool(memory_store))
    tool_registry.register(make_read_artifact_tool(artifact_store))

    # Register web search if configured
    web_search_tool = make_web_search_tool(cfg.web_search)
    if web_search_tool is not None:
        tool_registry.register(web_search_tool)

    # Register email tools if configured
    for email_tool in make_email_tools(cfg.email):
        tool_registry.register(email_tool)

    email_search_and_read = make_email_search_and_read_tool(
        EmailAdapter(cfg.email)
    )
    if email_search_and_read is not None:
        tool_registry.register(email_search_and_read)

    # Create typed context stores first
    failure_store = FailureStore(db)
    scheduler_store = SchedulerStore(db)
    trace_store = TraceStore(db)
    skill_store = SkillStore(db)
    proposal_store = ProposalStore(db)
    style_store = StyleProfileStore(db)
    style_builder = StyleProfileBuilder(db, style_store, cfg.style)

    # Initialize memory epoch compiler
    epoch_compiler = MemoryEpochCompiler(memory_store, max_tokens=500)

    # Initialize skill index builder
    skill_index_builder = SkillIndexBuilder(skill_store)

    app = CliAppContext(
        config=cfg,
        db=db,
        session_store=session_store,
        tool_registry=tool_registry,
        policy=policy,
        memory_store=memory_store,
        failure_store=failure_store,
        trace_store=trace_store,
        artifact_store=artifact_store,
        scheduler_store=scheduler_store,
        skill_store=skill_store,
        proposal_store=proposal_store,
        style_store=style_store,
        style_builder=style_builder,
        epoch_compiler=epoch_compiler,
        skill_index_builder=skill_index_builder,
        verbose=cfg.verbose,
        confirm_callback=None,
        calibration_path=calibration_path,
        compiled_identity=compiled_identity,
    )

    # Register delegate task tool (needs app for orchestrator factory)
    tool_registry.register(make_delegate_task_tool(session_store, app.make_orchestrator))

    return app


def run_async(coro_factory: Callable[..., Awaitable[Any]]) -> Callable[..., Any]:
    """Decorator: wrap a Click command body so the inner async function
    receives ``app`` and is run inside ``asyncio.run``. Calls ``bootstrap_db`` once.
    """
    @functools.wraps(coro_factory)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = click.get_current_context()
        app: CliAppContext = ctx.obj
        async def _runner() -> Any:
            await app.bootstrap_db()
            return await coro_factory(app, *args, **kwargs)
        return asyncio.run(_runner())
    return wrapper

