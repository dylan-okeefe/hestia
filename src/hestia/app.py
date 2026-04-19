"""Application bootstrap and context for Hestia CLI."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import click
import httpx

from hestia.artifacts.store import ArtifactStore
from hestia.config import HestiaConfig
from hestia.context.builder import ContextBuilder
from hestia.context.compressor import InferenceHistoryCompressor
from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, ScheduledTask, Session, SessionState, SessionTemperature
from hestia.email.adapter import EmailAdapter
from hestia.errors import HestiaError
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
from hestia.policy.default import DEFAULT_DELEGATION_KEYWORDS, DefaultPolicyEngine
from hestia.reflection.runner import ReflectionRunner
from hestia.reflection.scheduler import ReflectionScheduler
from hestia.reflection.store import ProposalStore
from hestia.scheduler import Scheduler
from hestia.security import InjectionScanner
from hestia.skills.index import SkillIndexBuilder
from hestia.skills.state import SkillState
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
from hestia.tools.capabilities import (
    EMAIL_SEND,
    MEMORY_READ,
    MEMORY_WRITE,
    NETWORK_EGRESS,
    SHELL_EXEC,
    WRITE_LOCAL,
)
from hestia.tools.registry import ToolNotFoundError, ToolRegistry

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
                    InferenceHistoryCompressor(self.inference, max_chars=self.config.compression.max_chars)
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

async def _cmd_chat(app: CliAppContext) -> None:
    """Start an interactive chat session."""
    if not app.config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    app.confirm_callback = CliConfirmHandler()
    orchestrator = app.make_orchestrator()

    # Recover stale turns from previous crash
    recovered = await orchestrator.recover_stale_turns()
    if recovered:
        click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

    session = await app.session_store.get_or_create_session("cli", "default")
    click.echo(f"Session: {session.id}")

    compiled = await _compile_and_set_memory_epoch(app, session)
    if compiled:
        click.echo("Memory epoch compiled.")

    click.echo("Type 'exit' or 'quit' to end the session, or /help for commands.\n")

    from hestia.app import CliResponseHandler

    response_handler = CliResponseHandler(verbose=app.verbose)

    while True:
        try:
            user_input = click.prompt("You", type=str).strip()
            if user_input.lower() in ("exit", "quit"):
                break
            if user_input.startswith("/"):
                should_exit, session = await _handle_meta_command(
                    user_input, session, app.session_store, app
                )
                if should_exit:
                    break
                continue

            user_message = Message(role="user", content=user_input)
            await orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=response_handler,
            )
        except KeyboardInterrupt:
            click.echo("\nUse /quit or /exit to end the session.")
        except (HestiaError, httpx.HTTPError, OSError) as e:
            click.echo(f"Error: {e}", err=True)
            if app.verbose:
                import traceback

                traceback.print_exc()

    click.echo("Goodbye!")

async def _cmd_ask(app: CliAppContext, message: str) -> None:
    """Send a single message and get a response."""
    if not app.config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    app.confirm_callback = CliConfirmHandler()
    orchestrator = app.make_orchestrator()

    recovered = await orchestrator.recover_stale_turns()
    if recovered:
        click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

    session = await app.session_store.get_or_create_session("cli", "default")
    await _compile_and_set_memory_epoch(app, session)

    user_message = Message(role="user", content=message)

    from hestia.app import CliResponseHandler

    response_handler = CliResponseHandler(verbose=app.verbose)

    await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=response_handler,
    )

async def _cmd_health(app: CliAppContext) -> None:
    """Check inference server health."""
    try:
        health_info = await app.inference.health()
        click.echo("Inference server is healthy:")
        for key, value in health_info.items():
            click.echo(f"  {key}: {value}")
    except (HestiaError, httpx.HTTPError, OSError) as e:
        click.echo(f"Health check failed: {e}", err=True)
        sys.exit(1)
    finally:
        await app.inference.close()

async def _cmd_status(app: CliAppContext) -> None:
    """Show system status summary."""
    cfg = app.config
    store = _require_scheduler_store(app)

    # 1. Inference health
    click.echo("Inference:")
    try:
        health_info = await app.inference.health()
        click.echo("  Status: ok")
        for key, value in health_info.items():
            click.echo(f"  {key}: {value}")
    except (HestiaError, httpx.HTTPError, OSError) as e:
        click.echo(f"  Status: failed ({e})")

    # 2. Sessions by state
    click.echo("\nSessions:")
    session_counts = await app.session_store.count_sessions_by_state()
    if session_counts:
        for state, count in sorted(session_counts.items()):
            click.echo(f"  {state}: {count}")
    else:
        click.echo("  No sessions")

    # 3. Turns in last 24h
    click.echo("\nTurns (last 24h):")
    since = utcnow() - timedelta(hours=24)
    turn_stats = await app.session_store.turn_stats_since(since)
    if turn_stats:
        for state, count in sorted(turn_stats.items()):
            click.echo(f"  {state}: {count}")
    else:
        click.echo("  No turns")

    # 4. Scheduled tasks
    click.echo("\nScheduled Tasks:")
    stats = await store.summary_stats()
    click.echo(f"  Enabled: {stats['enabled_count']}")
    if stats["next_run_at"]:
        next_run = stats["next_run_at"]
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=UTC)
        click.echo(f"  Next due: {next_run.astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    else:
        click.echo("  Next due: none")

    # 5. Failures in last 24h
    click.echo("\nFailures (last 24h):")
    failure_counts = await app.failure_store.count_by_class(since=since)
    if failure_counts:
        for failure_class, count in sorted(failure_counts.items()):
            click.echo(f"  {failure_class}: {count}")
    else:
        click.echo("  No failures")

    await app.inference.close()

async def _cmd_failures_list(app: CliAppContext, limit: int, failure_class: str | None) -> None:
    """List recent failures."""
    bundles = await app.failure_store.list_recent(limit=limit, failure_class=failure_class)
    if not bundles:
        click.echo("No failures found.")
        return
    for bundle in bundles:
        click.echo(f"\nID: {bundle.id}")
        click.echo(f"  Time: {bundle.created_at}")
        click.echo(f"  Class: {bundle.failure_class} (severity: {bundle.severity})")
        click.echo(f"  Session: {bundle.session_id}")
        click.echo(f"  Turn: {bundle.turn_id}")
        click.echo(f"  Message: {bundle.error_message[:100]}")
        if len(bundle.error_message) > 100:
            click.echo("  ...")

async def _cmd_failures_summary(app: CliAppContext, days: int) -> None:
    """Show failure counts by class."""
    since = utcnow() - timedelta(days=days)
    counts = await app.failure_store.count_by_class(since=since)
    click.echo(f"Failure summary (last {days} days):\n")
    if counts:
        total = sum(counts.values())
        for failure_class, count in sorted(counts.items(), key=lambda x: -x[1]):
            click.echo(f"  {failure_class}: {count}")
        click.echo(f"\nTotal: {total}")
    else:
        click.echo("  No failures in this period.")

async def _cmd_schedule_add(
        app: CliAppContext,
        cron: str | None,
        fire_at_str: str | None,
        description: str | None,
        session_id: str | None,
        platform: str | None,
        platform_user: str | None,
        prompt: str,
    ) -> None:
        """Add a scheduled task."""
        if cron is not None and fire_at_str is not None:
            click.echo("Error: Cannot specify both --cron and --at", err=True)
            sys.exit(1)
        if cron is None and fire_at_str is None:
            click.echo("Error: Must specify either --cron or --at", err=True)
            sys.exit(1)
        if session_id is not None and (platform is not None or platform_user is not None):
            click.echo("Error: Cannot use --session-id with --platform or --platform-user", err=True)
            sys.exit(1)
        if (platform is not None) != (platform_user is not None):
            click.echo("Error: --platform and --platform-user must be used together", err=True)
            sys.exit(1)

        fire_at: datetime | None = None
        if fire_at_str is not None:
            try:
                fire_at = datetime.fromisoformat(fire_at_str)
            except ValueError:
                click.echo(
                    f"Error: Invalid datetime format '{fire_at_str}'. Use ISO format: 2026-04-15T15:00:00",
                    err=True,
                )
                sys.exit(1)
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(tzinfo=UTC)
            if fire_at < utcnow():
                click.echo(f"Error: Cannot schedule task in the past: {fire_at}", err=True)
                sys.exit(1)

        store = _require_scheduler_store(app)

        if session_id is not None:
            session = await app.session_store.get_session(session_id)
            if session is None:
                click.echo(f"Error: Session not found: {session_id}", err=True)
                sys.exit(1)
        elif platform is not None and platform_user is not None:
            session = await app.session_store.get_or_create_session(platform, platform_user)
        else:
            session = await app.session_store.get_or_create_session("cli", "default")

        try:
            task = await store.create_task(
                session_id=session.id,
                prompt=prompt,
                description=description,
                cron_expression=cron,
                fire_at=fire_at,
            )
            click.echo(f"Created task: {task.id}")
            click.echo(f"  Session: {task.session_id}")
            if task.cron_expression:
                click.echo(f"  Schedule: cron '{task.cron_expression}'")
            elif task.fire_at:
                click.echo(f"  Schedule: at {task.fire_at}")
            click.echo(f"  Next run: {task.next_run_at}")
        except (HestiaError, ValueError) as e:
            click.echo(f"Error creating task: {e}", err=True)
            sys.exit(1)

async def _cmd_schedule_list(app: CliAppContext) -> None:
    """List scheduled tasks."""
    store = _require_scheduler_store(app)
    tasks = await store.list_tasks_for_session(session_id=None, include_disabled=True)
    if not tasks:
        click.echo("No scheduled tasks.")
        return
    click.echo(f"{'ID':<20} {'Description':<25} {'Schedule':<20} {'Enabled':<8} {'Next Run'}")
    click.echo("-" * 95)
    for task in tasks:
        desc = (task.description or "")[:24]
        if task.cron_expression:
            sched = f"cron: {task.cron_expression[:16]}"
        elif task.fire_at:
            fire_at = task.fire_at
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(tzinfo=UTC)
            sched = f"at: {fire_at.astimezone().strftime('%Y-%m-%d %H:%M')[:16]}"
        else:
            sched = "unknown"
        enabled = "yes" if task.enabled else "no"
        if task.next_run_at:
            next_run_dt = task.next_run_at
            if next_run_dt.tzinfo is None:
                next_run_dt = next_run_dt.replace(tzinfo=UTC)
            next_run = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M")
        else:
            next_run = "-"
        click.echo(f"{task.id:<20} {desc:<25} {sched:<20} {enabled:<8} {next_run}")

def _format_datetime(dt: datetime | None) -> str:
    """Format a datetime for display in the CLI."""
    if dt is None:
        return "N/A"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")


async def _cmd_schedule_show(app: CliAppContext, task_id: str) -> None:
    """Show details of a scheduled task."""
    store = _require_scheduler_store(app)
    task = await store.get_task(task_id)
    if task is None:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    click.echo(f"ID:          {task.id}")
    click.echo(f"Session:     {task.session_id}")
    click.echo(f"Prompt:      {task.prompt}")
    if task.description:
        click.echo(f"Description: {task.description}")
    if task.cron_expression:
        click.echo(f"Schedule:    cron '{task.cron_expression}'")
    elif task.fire_at:
        click.echo(f"Schedule:    at {_format_datetime(task.fire_at)}")
    click.echo(f"Enabled:     {'yes' if task.enabled else 'no'}")
    click.echo(f"Next run:    {_format_datetime(task.next_run_at)}")
    click.echo(f"Last run:    {_format_datetime(task.last_run_at)}")
    if task.last_error:
        click.echo(f"Last error:  {task.last_error}")

async def _cmd_schedule_enable(app: CliAppContext, task_id: str) -> None:
    """Enable a scheduled task."""
    store = _require_scheduler_store(app)
    success = await store.set_enabled(task_id, True)
    if not success:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    click.echo(f"Task {task_id} enabled")

async def _cmd_schedule_run(app: CliAppContext, task_id: str) -> None:
    """Manually trigger a scheduled task."""
    store = _require_scheduler_store(app)
    task = await store.get_task(task_id)
    if task is None:
        click.echo(f"Task not found: {task_id}", err=True)
        sys.exit(1)
    orchestrator = app.make_orchestrator()

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[{task.id}] {text}")

    scheduler = Scheduler(
        scheduler_store=store,
        session_store=app.session_store,
        orchestrator=orchestrator,
        response_callback=response_callback,
    )
    try:
        await scheduler.run_now(task_id)
        click.echo(f"Task {task_id} executed successfully")
    except (HestiaError, httpx.HTTPError, OSError) as e:
        click.echo(f"Error running task: {e}", err=True)
        sys.exit(1)

def _cmd_schedule_daemon(ctx: click.Context, tick_interval: float | None) -> None:
    """Run the scheduler daemon (blocks until Ctrl-C)."""
    app: CliAppContext = ctx.obj
    # Headless daemon — no confirmation callback
    app.confirm_callback = None
    cfg = app.config
    tick = tick_interval if tick_interval is not None else cfg.scheduler.tick_interval_seconds

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[scheduler:{task.id}] {text}")

    async def _daemon() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)
        orchestrator = app.make_orchestrator()
        scheduler = Scheduler(
            scheduler_store=store,
            session_store=app.session_store,
            orchestrator=orchestrator,
            response_callback=response_callback,
            tick_interval_seconds=tick,
        )
        await scheduler.start()
        click.echo(f"Scheduler daemon started (tick={tick}s). Press Ctrl-C to stop.")
        try:
            while True:
                await asyncio.sleep(60)
                if app.config.reflection.enabled and app.reflection_scheduler is not None:
                    await app.reflection_scheduler.tick()
                if app.style_scheduler is not None:
                    await app.style_scheduler.tick()
        except asyncio.CancelledError:
            pass
        finally:
            click.echo("\nShutting down scheduler...")
            await scheduler.stop()

    def run_daemon() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        main_task = loop.create_task(_daemon())
        try:
            loop.run_until_complete(main_task)
        except KeyboardInterrupt:
            click.echo("\nReceived interrupt signal...")
            main_task.cancel()
            try:
                loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                pass
        finally:
            loop.run_until_complete(app.inference.close())
            loop.close()

    run_daemon()

async def _cmd_skill_list(app: CliAppContext, state_filter: str | None, show_all: bool) -> None:
    """List skills with their states."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    skill_state = None
    if state_filter:
        try:
            skill_state = SkillState(state_filter.lower())
        except ValueError:
            click.echo(f"Invalid state: {state_filter}", err=True)
            sys.exit(1)
    records = await app.skill_store.list_all(
        state=skill_state,
        exclude_disabled=not show_all,
    )
    if not records:
        click.echo("No skills found.")
        return
    click.echo(f"{'Name':<20} {'State':<12} {'Runs':<6} {'Fails':<6} {'Description'}")
    click.echo("-" * 80)
    for record in records:
        desc = record.description[:35] + "..." if len(record.description) > 35 else record.description
        click.echo(
            f"{record.name:<20} {record.state.value:<12} "
            f"{record.run_count:<6} {record.failure_count:<6} {desc}"
        )

async def _cmd_skill_show(app: CliAppContext, name: str) -> None:
    """Show skill details."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    click.echo(f"Name:        {record.name}")
    click.echo(f"Description: {record.description}")
    click.echo(f"State:       {record.state.value}")
    click.echo(f"File path:   {record.file_path}")
    click.echo(f"Created:     {record.created_at}")
    click.echo(f"Last run:    {record.last_run_at or 'Never'}")
    click.echo(f"Run count:   {record.run_count}")
    click.echo(f"Failures:    {record.failure_count}")
    click.echo(f"Tools:       {', '.join(record.required_tools) or 'none'}")
    click.echo(f"Caps:        {', '.join(record.capabilities) or 'none'}")

async def _cmd_skill_promote(app: CliAppContext, name: str) -> None:
    """Advance skill state (draft -> tested -> trusted)."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    transitions = {
        SkillState.DRAFT: SkillState.TESTED,
        SkillState.TESTED: SkillState.TRUSTED,
        SkillState.TRUSTED: SkillState.TRUSTED,
        SkillState.DEPRECATED: SkillState.TESTED,
        SkillState.DISABLED: SkillState.DRAFT,
    }
    new_state = transitions.get(record.state)
    if new_state is None:
        click.echo(f"Skill '{name}' has no valid promotion path from '{record.state.value}'", err=True)
        sys.exit(1)
    if new_state == record.state:
        click.echo(f"Skill '{name}' is already at state '{record.state.value}'")
        return
    await app.skill_store.update_state(name, new_state)
    click.echo(f"Promoted '{name}': {record.state.value} -> {new_state.value}")

async def _cmd_skill_demote(app: CliAppContext, name: str) -> None:
    """Move skill back one state."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    transitions = {
        SkillState.DRAFT: SkillState.DISABLED,
        SkillState.TESTED: SkillState.DRAFT,
        SkillState.TRUSTED: SkillState.TESTED,
        SkillState.DEPRECATED: SkillState.DEPRECATED,
        SkillState.DISABLED: SkillState.DISABLED,
    }
    new_state = transitions.get(record.state)
    if new_state is None:
        click.echo(f"Skill '{name}' has no valid demotion path from '{record.state.value}'", err=True)
        sys.exit(1)
    if new_state == record.state:
        click.echo(f"Skill '{name}' is already at state '{record.state.value}'")
        return
    await app.skill_store.update_state(name, new_state)
    click.echo(f"Demoted '{name}': {record.state.value} -> {new_state.value}")

async def _cmd_skill_disable(app: CliAppContext, name: str) -> None:
    """Disable a skill without removing it."""
    if app.skill_store is None:
        click.echo("Skill store not available", err=True)
        sys.exit(1)
    record = await app.skill_store.get_by_name(name)
    if record is None:
        click.echo(f"Skill not found: {name}", err=True)
        sys.exit(1)
    if record.state == SkillState.DISABLED:
        click.echo(f"Skill '{name}' is already disabled")
        return
    await app.skill_store.update_state(name, SkillState.DISABLED)
    click.echo(f"Disabled skill: {name}")

async def _cmd_audit_run(app: CliAppContext, output_json: bool, output: str | None) -> None:
    """Run security audit checks."""
    from hestia.audit import SecurityAuditor

    auditor = SecurityAuditor(
        config=app.config,
        tool_registry=app.tool_registry,
        trace_store=app.trace_store,
    )
    report = await auditor.run_audit()
    if output_json:
        result = report.to_json()
    else:
        result = report.summary()
    if output:
        Path(output).write_text(result)
        click.echo(f"Audit report saved to: {output}")
    else:
        click.echo(result)
    critical_count = sum(1 for f in report.findings if f.severity == "critical")
    if critical_count > 0:
        sys.exit(1)

async def _cmd_audit_egress(app: CliAppContext, since: str) -> None:
    """Print domain-level egress aggregation."""
    since_dt = _parse_since(since)
    rows = await app.trace_store.egress_summary(since=since_dt)
    if not rows:
        click.echo("No egress events found in the given window.")
        return
    click.echo(f"Egress summary since {since_dt.isoformat()}\n")
    click.echo(f"{'Domain':<40} {'Requests':>10} {'Failures':>10} {'Anomaly'}")
    click.echo("-" * 80)
    for row in rows:
        domain = row["domain"]
        total = row["total_requests"]
        failures = row["failure_count"]
        anomaly = ""
        if total < 3:
            anomaly = "LOW_VOLUME"
        click.echo(f"{domain:<40} {total:>10} {failures:>10} {anomaly}")

async def _cmd_email_check(app: CliAppContext) -> None:
    """Check email connectivity (IMAP login test)."""
    cfg = app.config
    if not cfg.email.imap_host:
        click.echo("Email is not configured. Set email.imap_host in your config.", err=True)
        sys.exit(1)
    from hestia.email.adapter import EmailAdapter

    adapter = EmailAdapter(cfg.email)
    try:
        messages = await adapter.list_messages(limit=1)
    except Exception as exc:
        click.echo(f"Email check failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)
    click.echo(f"IMAP connection OK ({cfg.email.imap_host}:{cfg.email.imap_port})")
    click.echo(f"Default folder: {cfg.email.default_folder}")
    click.echo(f"Messages found: {len(messages)}")

async def _cmd_email_list_cmd(app: CliAppContext, folder: str, limit: int, unread_only: bool) -> None:
    """List recent emails."""
    cfg = app.config
    if not cfg.email.imap_host:
        click.echo("Email is not configured.", err=True)
        sys.exit(1)
    from hestia.email.adapter import EmailAdapter

    adapter = EmailAdapter(cfg.email)
    try:
        messages = await adapter.list_messages(folder=folder, limit=limit, unread_only=unread_only)
    except Exception as exc:
        click.echo(f"Failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)
    if not messages:
        click.echo("No messages found.")
        return
    for m in messages:
        click.echo(f"[{m['message_id']}] {m['from']} | {m['subject']} | {m['date']}")

async def _cmd_email_read_cmd(app: CliAppContext, message_id: str) -> None:
    """Read a single email by IMAP UID."""
    cfg = app.config
    if not cfg.email.imap_host:
        click.echo("Email is not configured.", err=True)
        sys.exit(1)
    from hestia.email.adapter import EmailAdapter

    adapter = EmailAdapter(cfg.email)
    try:
        result = await adapter.read_message(message_id)
    except Exception as exc:
        click.echo(f"Failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(1)
    headers = result["headers"]
    click.echo(f"From: {headers['from']}")
    click.echo(f"To: {headers['to']}")
    click.echo(f"Subject: {headers['subject']}")
    click.echo(f"Date: {headers['date']}")
    click.echo("")
    click.echo(result["body"])
    if result["attachments"]:
        click.echo("")
        click.echo("Attachments:")
        for att in result["attachments"]:
            click.echo(f"  - {att['filename']} ({att['content_type']})")

async def _cmd_style_show(app: CliAppContext, platform: str | None, user: str | None) -> None:
    """Pretty-print the current style profile for a user."""
    if app.style_store is None:
        click.echo("Style store not available", err=True)
        sys.exit(1)
    platform = platform or "cli"
    platform_user = user or "default"
    metrics = await app.style_store.list_metrics(platform, platform_user)
    if not metrics:
        click.echo(f"No style profile found for {platform}/{platform_user}.")
        return
    click.echo(f"Style profile for {platform}/{platform_user}:")
    for m in metrics:
        click.echo(f"  {m.metric}: {m.value_json}")
    if app.style_scheduler is not None:
        sched_status = app.style_scheduler.status()
        if not sched_status["ok"]:
            click.echo("")
            click.echo("Failures:")
            click.echo(f"  Total: {sched_status['failure_count']}")
            for err in sched_status["last_errors"]:
                click.echo(f"  {err['timestamp']}  {err['type']:<20} {err['message']}")

async def _cmd_doctor(app: CliAppContext, plain: bool) -> int:
    """Run health checks. Returns exit code (0 if all green, 1 if any fail)."""
    from hestia.doctor import run_checks, render_results  # noqa: I001

    results = await run_checks(app)
    click.echo(render_results(results, plain=plain))
    return 0 if all(r.ok for r in results) else 1


async def _cmd_policy_show(app: CliAppContext) -> None:
    """Show current effective policy configuration."""
    cfg = app.config
    policy_engine = app.policy

    click.echo("=" * 60)
    click.echo("HESTIA EFFECTIVE POLICY")
    click.echo("=" * 60)
    click.echo("")

    # Reasoning budget
    click.echo("-" * 40)
    click.echo("REASONING BUDGETS")
    click.echo("-" * 40)
    click.echo(f"  Default: {cfg.inference.default_reasoning_budget} tokens")
    click.echo("  Subagent max: 1024 tokens (capped)")
    click.echo("")

    # Context window and budgets
    click.echo("-" * 40)
    click.echo("CONTEXT & COMPRESSION")
    click.echo("-" * 40)
    click.echo(f"  Context window: {policy_engine.ctx_window} tokens")
    synthetic_session = Session(
        id="diagnostic",
        platform="cli",
        platform_user="diagnostic",
        started_at=utcnow(),
        last_active_at=utcnow(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )
    click.echo(f"  Turn token budget: {policy_engine.turn_token_budget(synthetic_session)} tokens")
    click.echo("  Compression threshold: 85% of budget")
    click.echo("")

    # Trust profile
    click.echo("-" * 40)
    click.echo("TRUST PROFILE")
    click.echo("-" * 40)
    click.echo(f"  Active preset: {cfg.trust.preset or '(custom — no preset name)'}")
    click.echo(f"  auto_approve_tools: {cfg.trust.auto_approve_tools or '(none)'}")
    click.echo(f"  scheduler_shell_exec: {cfg.trust.scheduler_shell_exec}")
    click.echo(f"  scheduler_email_send: {cfg.trust.scheduler_email_send}")
    click.echo(f"  subagent_shell_exec: {cfg.trust.subagent_shell_exec}")
    click.echo(f"  subagent_write_local: {cfg.trust.subagent_write_local}")
    click.echo(f"  subagent_email_send: {cfg.trust.subagent_email_send}")
    click.echo("")

    # Tool filtering by session type
    click.echo("-" * 40)
    click.echo("TOOL AVAILABILITY BY SESSION TYPE")
    click.echo("-" * 40)
    session_types = [
        ("interactive (cli)", "cli"),
        ("subagent", "subagent"),
        ("scheduler", "scheduler"),
    ]
    all_tools = app.tool_registry.list_names()
    now = utcnow()
    for label, platform in session_types:
        session = Session(
            id="policy-show",
            platform=platform,
            platform_user="policy",
            started_at=now,
            last_active_at=now,
            slot_id=None,
            slot_saved_path=None,
            state=SessionState.ACTIVE,
            temperature=SessionTemperature.HOT,
        )
        allowed = policy_engine.filter_tools(session, all_tools, app.tool_registry)
        blocked = set(all_tools) - set(allowed)
        click.echo(f"\n  {label}:")
        click.echo(f"    Allowed ({len(allowed)}): {', '.join(sorted(allowed))}")
        if blocked:
            blocked_with_reasons = []
            for tool in sorted(blocked):
                try:
                    meta = app.tool_registry.describe(tool)
                    caps = set(meta.capabilities)
                    if platform == "subagent":
                        if SHELL_EXEC in caps:
                            reason = "shell_exec"
                        elif WRITE_LOCAL in caps:
                            reason = "write_local"
                        elif EMAIL_SEND in caps:
                            reason = "email_send"
                        else:
                            reason = "other"
                    elif platform == "scheduler":
                        if SHELL_EXEC in caps:
                            reason = "shell_exec"
                        elif EMAIL_SEND in caps:
                            reason = "email_send"
                        else:
                            reason = "other"
                    else:
                        reason = "unknown"
                    blocked_with_reasons.append(f"{tool} ({reason})")
                except ToolNotFoundError:
                    blocked_with_reasons.append(tool)
            click.echo(f"    Blocked ({len(blocked)}): {', '.join(blocked_with_reasons)}")
    click.echo("")

    # Capabilities summary
    click.echo("-" * 40)
    click.echo("TOOL CAPABILITIES")
    click.echo("-" * 40)
    capability_tools: dict[str, list[str]] = {
        SHELL_EXEC: [],
        NETWORK_EGRESS: [],
        WRITE_LOCAL: [],
        MEMORY_READ: [],
        MEMORY_WRITE: [],
        EMAIL_SEND: [],
    }
    for tool in all_tools:
        try:
            meta = app.tool_registry.describe(tool)
            for cap in meta.capabilities:
                if cap in capability_tools:
                    capability_tools[cap].append(tool)
        except ToolNotFoundError:
            pass
    for cap, tools in capability_tools.items():
        if tools:
            click.echo(f"  {cap}: {', '.join(sorted(tools))}")
    click.echo("")

    # Delegation settings
    click.echo("-" * 40)
    click.echo("DELEGATION POLICY")
    click.echo("-" * 40)
    click.echo("  Delegation triggers:")
    click.echo("    - Tool chain > 5 calls")
    delegation_keywords = (
        cfg.policy.delegation_keywords
        if cfg.policy.delegation_keywords is not None
        else DEFAULT_DELEGATION_KEYWORDS
    )
    click.echo(f"    - Keywords: {', '.join(delegation_keywords)}")
    # TODO(L38): consolidate research keywords through PolicyConfig
    click.echo("    - Research keywords: research, investigate, analyze deeply, comprehensive")
    click.echo("    - Projected tool calls > 3")
    click.echo("  Subagent restrictions:")
    click.echo("    - Cannot delegate further (no recursion)")
    click.echo("    - Reduced reasoning budget")
    click.echo("")

    # Confirmation requirements
    click.echo("-" * 40)
    click.echo("CONFIRMATION REQUIREMENTS")
    click.echo("-" * 40)
    confirming = sorted(
        name
        for name in app.tool_registry.list_names()
        if app.tool_registry.describe(name).requires_confirmation
    )
    click.echo("  Tools requiring confirmation (interactive only):")
    if confirming:
        for name in confirming:
            click.echo(f"    - {name}")
    else:
        click.echo("    - (none)")
    click.echo("  Platforms with confirmation:")
    click.echo("    - cli: Yes (interactive prompt)")
    click.echo("    - telegram: No (tools requiring confirmation will fail)")
    click.echo("    - matrix: No (tools requiring confirmation will fail)")
    click.echo("    - scheduler: No (shell_exec blocked entirely)")
    click.echo("")

    # Retry policy
    click.echo("-" * 40)
    click.echo("RETRY POLICY")
    click.echo("-" * 40)
    click.echo(f"  Max attempts: {policy_engine.retry_max_attempts}")
    click.echo("  Transient errors (retry with backoff):")
    click.echo("    - InferenceTimeoutError")
    click.echo("    - InferenceServerError")
    click.echo("  Non-transient errors (fail immediately):")
    click.echo("    - All other exceptions")
    click.echo("")

    # Web search status
    click.echo("-" * 40)
    click.echo("WEB SEARCH")
    click.echo("-" * 40)
    if cfg.web_search.provider:
        click.echo(f"  Provider: {cfg.web_search.provider}")
        click.echo(f"  Max results: {cfg.web_search.max_results}")
    else:
        click.echo("  Web search: disabled")
    click.echo("")

async def _cmd_reflection_status(app: CliAppContext) -> None:
    """Show reflection scheduler health and proposal counts."""
    if app.reflection_scheduler is not None:
        sched_status = app.reflection_scheduler.status()
        ok = "ok" if sched_status["ok"] else "degraded"
        click.echo(f"Scheduler: {ok} ({sched_status['failure_count']} failure(s))")
        if sched_status["last_run_at"]:
            click.echo(f"Last run: {sched_status['last_run_at'].isoformat()}")
        else:
            click.echo("Last run: never")
        if sched_status["last_errors"]:
            click.echo("Last errors:")
            for err in sched_status["last_errors"]:
                click.echo(f"  {err['timestamp']}  {err['stage']:<10} {err['type']:<20} {err['message']}")
    else:
        click.echo("Scheduler: not configured (0 failures)")

    if app.proposal_store is not None:
        click.echo("")
        click.echo("Proposals:")
        counts = await app.proposal_store.count_by_status()
        for status in ("pending", "accepted", "rejected", "deferred", "expired"):
            click.echo(f"  {status}: {counts.get(status, 0)}")
    else:
        click.echo("Proposal store: not configured")

async def _cmd_reflection_list(app: CliAppContext, status: str) -> None:
    """List proposals."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    proposals = await app.proposal_store.list_by_status(status=status, limit=100)  # type: ignore[arg-type]
    if not proposals:
        click.echo("No proposals found.")
        return
    click.echo(f"{'ID':<20} {'Type':<18} {'Confidence':<12} {'Summary'}")
    click.echo("-" * 80)
    for p in proposals:
        summary = p.summary[:40] + "..." if len(p.summary) > 40 else p.summary
        click.echo(f"{p.id:<20} {p.type:<18} {p.confidence:<12.2f} {summary}")

async def _cmd_reflection_show(app: CliAppContext, proposal_id: str) -> None:
    """Show full details of a proposal."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    click.echo(f"ID:          {p.id}")
    click.echo(f"Type:        {p.type}")
    click.echo(f"Status:      {p.status}")
    click.echo(f"Confidence:  {p.confidence:.2f}")
    click.echo(f"Created:     {p.created_at}")
    click.echo(f"Expires:     {p.expires_at}")
    click.echo(f"Evidence:    {', '.join(p.evidence)}")
    click.echo(f"Summary:     {p.summary}")
    click.echo(f"Action:      {p.action}")
    if p.review_note:
        click.echo(f"Review note: {p.review_note}")

async def _cmd_reflection_accept(app: CliAppContext, proposal_id: str) -> None:
    """Accept a proposal (marks it accepted; does not auto-apply)."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    await app.proposal_store.update_status(proposal_id, "accepted", review_note="Accepted by operator")
    click.echo(f"Accepted proposal {proposal_id}")

async def _cmd_reflection_reject(app: CliAppContext, proposal_id: str, note: str | None) -> None:
    """Reject a proposal."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    await app.proposal_store.update_status(
        proposal_id, "rejected", review_note=note or "Rejected by operator"
    )
    click.echo(f"Rejected proposal {proposal_id}")

async def _cmd_reflection_defer(app: CliAppContext, proposal_id: str, until: str | None) -> None:
    """Defer a proposal."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    p = await app.proposal_store.get(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        sys.exit(1)
    note = "Deferred by operator"
    if until:
        note = f"Deferred by operator until {until}"
    await app.proposal_store.update_status(proposal_id, "deferred", review_note=note)
    click.echo(f"Deferred proposal {proposal_id}")

async def _cmd_reflection_run(app: CliAppContext, now: bool) -> None:
    """Run reflection manually (requires --now)."""
    if not now:
        click.echo("Use --now to trigger reflection manually.", err=True)
        sys.exit(1)
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    from hestia.config import ReflectionConfig
    from hestia.reflection.runner import ReflectionRunner

    cfg = app.config.reflection
    manual_cfg = ReflectionConfig(
        enabled=True,
        cron=cfg.cron,
        idle_minutes=cfg.idle_minutes,
        lookback_turns=cfg.lookback_turns,
        proposals_per_run=cfg.proposals_per_run,
        expire_days=cfg.expire_days,
        model_override=cfg.model_override,
    )
    runner = ReflectionRunner(
        config=manual_cfg,
        inference=app.inference,
        trace_store=app.trace_store,
        proposal_store=app.proposal_store,
    )
    proposals = await runner.run()
    if proposals:
        click.echo(f"Generated {len(proposals)} proposal(s):")
        for p in proposals:
            click.echo(f"  - {p.id}: {p.type} ({p.confidence:.2f}) {p.summary[:60]}")
    else:
        click.echo("No proposals generated.")

async def _cmd_reflection_history(app: CliAppContext) -> None:
    """Show past proposals and their outcomes."""
    if app.proposal_store is None:
        click.echo("Proposal store not configured.", err=True)
        sys.exit(1)
    proposals = await app.proposal_store.list_by_status(limit=100)
    if not proposals:
        click.echo("No proposals found.")
        return
    click.echo(f"{'ID':<20} {'Type':<18} {'Status':<12} {'Confidence':<12} {'Summary'}")
    click.echo("-" * 90)
    for p in proposals:
        summary = p.summary[:35] + "..." if len(p.summary) > 35 else p.summary
        click.echo(f"{p.id:<20} {p.type:<18} {p.status:<12} {p.confidence:<12.2f} {summary}")


def _parse_since(since: str) -> datetime:
    """Convert a human-readable window like '7d' or '24h' to a datetime."""
    now = datetime.now(UTC)
    if since.endswith("d"):
        days = int(since[:-1])
        return now - timedelta(days=days)
    if since.endswith("h"):
        hours = int(since[:-1])
        return now - timedelta(hours=hours)
    # fallback: assume days
    return now - timedelta(days=int(since))
