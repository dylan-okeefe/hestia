"""CLI adapter for Hestia - local-first LLM agent framework."""

import asyncio
import logging
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Callable, Coroutine
from typing import Any

import click
import httpx

from hestia.artifacts.store import ArtifactStore
from hestia.config import HestiaConfig
from hestia.security import InjectionScanner
from hestia.context.builder import ContextBuilder
from hestia.context.compressor import InferenceHistoryCompressor
from hestia.core.clock import utcnow
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, ScheduledTask, Session
from hestia.errors import HestiaError
from hestia.identity import IdentityCompiler
from hestia.inference import SlotManager
from hestia.logging_config import setup_logging
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
from hestia.scheduler import Scheduler
from hestia.skills.index import SkillIndexBuilder
from hestia.skills.state import SkillState
from hestia.tools.builtin import (
    current_time,
    http_get,
    make_delegate_task_tool,
    make_email_tools,
    make_list_dir_tool,
    make_list_memories_tool,
    make_read_file_tool,
    make_save_memory_tool,
    make_search_memory_tool,
    make_web_search_tool,
    make_write_file_tool,
    terminal,
)
from hestia.tools.registry import ToolNotFoundError, ToolRegistry

logger = logging.getLogger(__name__)

# Path to calibration file (not configurable via CLI)
DEFAULT_CALIBRATION_PATH = Path("docs/calibration.json")


def _make_policy(cfg: HestiaConfig) -> DefaultPolicyEngine:
    """Build the policy engine from config."""
    return DefaultPolicyEngine(
        ctx_window=cfg.inference.context_length,
        default_reasoning_budget=cfg.inference.default_reasoning_budget,
        trust=cfg.trust,
    )


class CliResponseHandler:
    """Handles responses from the orchestrator in CLI mode."""

    def __init__(self, verbose: bool = False):
        """Initialize with verbosity flag."""
        self.verbose = verbose

    async def __call__(self, response: str) -> None:
        """Print response to stdout."""
        click.echo(f"\nAssistant: {response}\n")


async def _bootstrap_db(
    db: Database,
    memory_store: MemoryStore,
    failure_store: FailureStore,
    trace_store: TraceStore | None = None,
) -> None:
    """Connect to database and create tables for daemon/bot commands.

    This standalone helper is used by commands that don't use CliAppContext.
    """
    await db.connect()
    await db.create_tables()
    await memory_store.create_table()
    await failure_store.create_table()
    if trace_store is not None:
        await trace_store.create_table()


@dataclass
class CliAppContext:
    """Typed application context shared across CLI commands."""

    config: HestiaConfig
    db: Database
    inference: InferenceClient
    session_store: SessionStore
    context_builder: ContextBuilder
    tool_registry: ToolRegistry
    policy: DefaultPolicyEngine
    slot_manager: SlotManager
    memory_store: MemoryStore
    failure_store: FailureStore
    trace_store: TraceStore
    scheduler_store: SchedulerStore | None = None
    skill_store: SkillStore | None = None
    verbose: bool = False
    confirm_callback: Any = None
    epoch_compiler: MemoryEpochCompiler | None = None
    skill_index_builder: SkillIndexBuilder | None = None
    handoff_summarizer: SessionHandoffSummarizer | None = None

    async def bootstrap_db(self) -> None:
        """Connect to database and create tables."""
        await self.db.connect()
        await self.db.create_tables()
        await self.memory_store.create_table()
        await self.failure_store.create_table()
        await self.trace_store.create_table()
        if self.skill_store is not None:
            await self.skill_store.create_table()

    def make_injection_scanner(self) -> InjectionScanner:
        """Create an InjectionScanner from config."""
        return InjectionScanner(
            enabled=self.config.security.injection_scanner_enabled,
            entropy_threshold=self.config.security.injection_entropy_threshold,
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
        )


def _require_scheduler_store(app: CliAppContext) -> SchedulerStore:
    """Return the scheduler store or raise a clear error."""
    if app.scheduler_store is None:
        raise click.UsageError(
            "Scheduler is not configured. Set `scheduler.enabled = True` in your config."
        )
    return app.scheduler_store


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


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to Hestia config file (Python)",
)
@click.option("--db-path", type=click.Path(), default=None)
@click.option("--artifacts-path", type=click.Path(), default=None)
@click.option("--slot-dir", type=click.Path(), default=None)
@click.option("--slot-pool-size", type=int, default=None)
@click.option("--inference-url", default=None)
@click.option("--model", default=None)
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.pass_context
def cli(
    ctx: click.Context,
    config_path: str | None,
    db_path: str | None,
    artifacts_path: str | None,
    slot_dir: str | None,
    slot_pool_size: int | None,
    inference_url: str | None,
    model: str | None,
    verbose: bool,
) -> None:
    """Hestia - Local-first LLM agent framework."""
    ctx.ensure_object(dict)
    ctx.obj["confirm_callback"] = None

    # Load config
    if config_path:
        cfg = HestiaConfig.from_file(Path(config_path))
    else:
        cfg = HestiaConfig.default()

    # Apply CLI overrides (only when explicitly provided)
    if db_path is not None:
        cfg.storage.database_url = f"sqlite+aiosqlite:///{db_path}"
    if artifacts_path is not None:
        cfg.storage.artifacts_dir = Path(artifacts_path)
    if slot_dir is not None:
        cfg.slots.slot_dir = Path(slot_dir)
    if slot_pool_size is not None:
        cfg.slots.pool_size = slot_pool_size
    if inference_url is not None:
        cfg.inference.base_url = inference_url
    if model is not None:
        cfg.inference.model_name = model
    if verbose:
        cfg.verbose = True

    # Setup logging after config is finalized
    setup_logging(cfg.verbose)

    # Build subsystems from config
    db = Database(cfg.storage.database_url)
    artifact_store = ArtifactStore(cfg.storage.artifacts_dir)
    # Allow empty model_name for commands that don't need inference; commands
    # that do will validate before use.
    model_name = cfg.inference.model_name or "dummy"
    inference = InferenceClient(cfg.inference.base_url, model_name)
    session_store = SessionStore(db)
    policy = _make_policy(cfg)

    # Compile identity from SOUL.md (default path) when present
    identity_compiler = IdentityCompiler(cfg.identity)
    compiled_identity = identity_compiler.get_compiled_text()

    # Context builder with calibration and optional identity
    calibration_path = Path("docs/calibration.json")
    context_builder = ContextBuilder.from_calibration_file(inference, policy, calibration_path)
    if compiled_identity:
        context_builder.set_identity_prefix(compiled_identity)

    # Overflow-recovery compression (L21). Off by default; opt in via CompressionConfig.
    if cfg.compression.enabled:
        context_builder.enable_compression(
            InferenceHistoryCompressor(inference, max_chars=cfg.compression.max_chars)
        )

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

    # Register web search if configured
    web_search_tool = make_web_search_tool(cfg.web_search)
    if web_search_tool is not None:
        tool_registry.register(web_search_tool)

    # Register email tools if configured
    for email_tool in make_email_tools(cfg.email):
        tool_registry.register(email_tool)

    # Slot manager for KV-cache persistence
    slot_manager = SlotManager(
        inference=inference,
        session_store=session_store,
        slot_dir=cfg.slots.slot_dir,
        pool_size=cfg.slots.pool_size,
    )

    # Create typed context stores first (needed by orchestrator_factory)
    failure_store = FailureStore(db)
    scheduler_store = SchedulerStore(db)
    trace_store = TraceStore(db)
    skill_store = SkillStore(db)

    # Session-close handoff summarizer (L21). Off by default; opt in via HandoffConfig.
    handoff_summarizer: SessionHandoffSummarizer | None = None
    if cfg.handoff.enabled:
        handoff_summarizer = SessionHandoffSummarizer(
            inference=inference,
            memory_store=memory_store,
            max_chars=cfg.handoff.max_chars,
            min_messages=cfg.handoff.min_messages,
        )

    scanner = InjectionScanner(
        enabled=cfg.security.injection_scanner_enabled,
        entropy_threshold=cfg.security.injection_entropy_threshold,
    )

    def orchestrator_factory() -> Orchestrator:
        """Fresh orchestrator for subagent turns (shares registry and stores)."""
        return Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=ctx.obj.get("confirm_callback"),
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
            failure_store=failure_store,
            trace_store=trace_store,
            handoff_summarizer=handoff_summarizer,
            injection_scanner=scanner,
        )

    tool_registry.register(make_delegate_task_tool(session_store, orchestrator_factory))

    # Initialize memory epoch compiler
    epoch_compiler = MemoryEpochCompiler(memory_store, max_tokens=500)

    # Initialize skill index builder
    skill_index_builder = SkillIndexBuilder(skill_store)

    ctx.obj["app"] = CliAppContext(
        config=cfg,
        db=db,
        inference=inference,
        session_store=session_store,
        context_builder=context_builder,
        tool_registry=tool_registry,
        policy=policy,
        slot_manager=slot_manager,
        memory_store=memory_store,
        failure_store=failure_store,
        trace_store=trace_store,
        scheduler_store=scheduler_store,
        skill_store=skill_store,
        verbose=cfg.verbose,
        confirm_callback=None,
        epoch_compiler=epoch_compiler,
        skill_index_builder=skill_index_builder,
        handoff_summarizer=handoff_summarizer,
    )

    # Also expose raw objects for daemon/bot commands that access ctx.obj directly
    ctx.obj["config"] = cfg
    ctx.obj["db"] = db
    ctx.obj["inference"] = inference
    ctx.obj["session_store"] = session_store
    ctx.obj["context_builder"] = context_builder
    ctx.obj["tool_registry"] = tool_registry
    ctx.obj["policy"] = policy
    ctx.obj["slot_manager"] = slot_manager
    ctx.obj["memory_store"] = memory_store
    ctx.obj["failure_store"] = failure_store
    ctx.obj["trace_store"] = trace_store
    ctx.obj["skill_store"] = skill_store





@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize database, artifacts, and slot directories."""
    app: CliAppContext = ctx.obj["app"]
    cfg = app.config

    async def _init() -> None:
        await app.bootstrap_db()
        cfg.storage.artifacts_dir.mkdir(parents=True, exist_ok=True)
        cfg.slots.slot_dir.mkdir(parents=True, exist_ok=True)
        click.echo(f"Initialized database at {cfg.storage.database_url}")
        click.echo(f"Initialized artifacts directory at {cfg.storage.artifacts_dir}")
        click.echo(f"Initialized slot directory at {cfg.slots.slot_dir}")

    asyncio.run(_init())


@cli.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start an interactive chat session."""
    app: CliAppContext = ctx.obj["app"]
    if not app.config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    app.confirm_callback = CliConfirmHandler()

    async def _chat() -> None:
        await app.bootstrap_db()
        orchestrator = app.make_orchestrator()

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        # Get or create session for CLI user
        session = await app.session_store.get_or_create_session("cli", "default")
        click.echo(f"Session: {session.id}")

        # Compile memory epoch for this session
        compiled = await _compile_and_set_memory_epoch(app, session)
        if compiled:
            click.echo("Memory epoch compiled.")

        click.echo("Type 'exit' or 'quit' to end the session, or /help for commands.\n")

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

    try:
        asyncio.run(_chat())
    finally:
        asyncio.run(app.inference.close())


@cli.command()
@click.argument("message")
@click.pass_context
def ask(ctx: click.Context, message: str) -> None:
    """Send a single message and get a response."""
    app: CliAppContext = ctx.obj["app"]
    if not app.config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    app.confirm_callback = CliConfirmHandler()

    async def _ask() -> None:
        await app.bootstrap_db()
        orchestrator = app.make_orchestrator()

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        session = await app.session_store.get_or_create_session("cli", "default")

        # Compile memory epoch for this session
        await _compile_and_set_memory_epoch(app, session)

        user_message = Message(role="user", content=message)

        response_handler = CliResponseHandler(verbose=app.verbose)

        await orchestrator.process_turn(
            session=session,
            user_message=user_message,
            respond_callback=response_handler,
        )

    try:
        asyncio.run(_ask())
    finally:
        asyncio.run(app.inference.close())


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check inference server health."""
    app: CliAppContext = ctx.obj["app"]

    async def _health() -> None:
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

    asyncio.run(_health())


@cli.command()
def version() -> None:
    """Show Hestia version."""
    from importlib.metadata import version as get_version

    click.echo(f"Hestia {get_version('hestia')}")
    click.echo(f"Python {sys.version}")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show system status summary."""
    app: CliAppContext = ctx.obj["app"]
    cfg = app.config

    async def _status() -> None:
        await app.bootstrap_db()
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
            # Convert UTC to local time for display
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

    asyncio.run(_status())


# Failures command group
@cli.group()
def failures() -> None:
    """View failure history."""
    pass


@failures.command(name="list")
@click.option("--limit", type=int, default=20, help="Maximum number of failures to show")
@click.option("--class", "failure_class", default=None, help="Filter by failure class")
@click.pass_context
def failures_list(ctx: click.Context, limit: int, failure_class: str | None) -> None:
    """List recent failures."""
    app: CliAppContext = ctx.obj["app"]

    async def _list() -> None:
        await app.bootstrap_db()

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

    asyncio.run(_list())


@failures.command(name="summary")
@click.option("--days", type=int, default=7, help="Number of days to summarize")
@click.pass_context
def failures_summary(ctx: click.Context, days: int) -> None:
    """Show failure counts by class."""
    app: CliAppContext = ctx.obj["app"]

    async def _summary() -> None:
        await app.bootstrap_db()

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

    asyncio.run(_summary())


# Schedule command group
@cli.group()
def schedule() -> None:
    """Manage scheduled tasks."""
    pass


@schedule.command(name="add")
@click.option("--cron", help="Cron expression (e.g., '0 9 * * 1-5' for weekdays at 9am)")
@click.option("--at", "fire_at_str", help="One-shot time (ISO format: 2026-04-15T15:00:00)")
@click.option("--description", "-d", help="Task description")
@click.option("--session-id", help="Bind task to an existing session ID")
@click.option("--platform", help="Platform for session binding (e.g., matrix)")
@click.option("--platform-user", help="Platform user for session binding (e.g., room ID)")
@click.argument("prompt")
@click.pass_context
def schedule_add(
    ctx: click.Context,
    cron: str | None,
    fire_at_str: str | None,
    description: str | None,
    session_id: str | None,
    platform: str | None,
    platform_user: str | None,
    prompt: str,
) -> None:
    """Add a scheduled task."""
    app: CliAppContext = ctx.obj["app"]

    # Validate exactly one of cron or fire_at
    if cron is not None and fire_at_str is not None:
        click.echo("Error: Cannot specify both --cron and --at", err=True)
        sys.exit(1)
    if cron is None and fire_at_str is None:
        click.echo("Error: Must specify either --cron or --at", err=True)
        sys.exit(1)

    # Validate session binding options
    if session_id is not None and (platform is not None or platform_user is not None):
        click.echo("Error: Cannot use --session-id with --platform or --platform-user", err=True)
        sys.exit(1)
    if (platform is not None) != (platform_user is not None):
        click.echo("Error: --platform and --platform-user must be used together", err=True)
        sys.exit(1)

    # Parse fire_at if provided
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

        # Reject past times (compare in UTC)
        if fire_at.tzinfo is None:
            fire_at = fire_at.replace(tzinfo=UTC)
        if fire_at < utcnow():
            click.echo(f"Error: Cannot schedule task in the past: {fire_at}", err=True)
            sys.exit(1)

    async def _add() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        # Resolve target session
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

    asyncio.run(_add())


@schedule.command(name="list")
@click.pass_context
def schedule_list(ctx: click.Context) -> None:
    """List scheduled tasks."""
    app: CliAppContext = ctx.obj["app"]

    async def _list() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        tasks = await store.list_tasks_for_session(session_id=None, include_disabled=True)

        if not tasks:
            click.echo("No scheduled tasks.")
            return

        # Print header
        click.echo(f"{'ID':<20} {'Description':<25} {'Schedule':<20} {'Enabled':<8} {'Next Run'}")
        click.echo("-" * 95)

        for task in tasks:
            desc = (task.description or "")[:24]
            if task.cron_expression:
                sched = f"cron: {task.cron_expression[:16]}"
            elif task.fire_at:
                # Convert UTC to local time for display
                fire_at = task.fire_at
                if fire_at.tzinfo is None:
                    fire_at = fire_at.replace(tzinfo=UTC)
                sched = f"at: {fire_at.astimezone().strftime('%Y-%m-%d %H:%M')[:16]}"
            else:
                sched = "unknown"
            enabled = "yes" if task.enabled else "no"
            if task.next_run_at:
                # Convert UTC to local time for display
                next_run_dt = task.next_run_at
                if next_run_dt.tzinfo is None:
                    next_run_dt = next_run_dt.replace(tzinfo=UTC)
                next_run = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M")
            else:
                next_run = "-"
            click.echo(f"{task.id:<20} {desc:<25} {sched:<20} {enabled:<8} {next_run}")

    asyncio.run(_list())


@schedule.command(name="show")
@click.argument("task_id")
@click.pass_context
def schedule_show(ctx: click.Context, task_id: str) -> None:
    """Show details of a scheduled task."""
    app: CliAppContext = ctx.obj["app"]

    def _format_datetime(dt: datetime | None) -> str:
        """Format datetime for display, converting UTC to local time."""
        if dt is None:
            return "-"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")

    async def _show() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        task = await store.get_task(task_id)

        if task is None:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        click.echo(f"ID:          {task.id}")
        click.echo(f"Session:     {task.session_id}")
        click.echo(f"Prompt:      {task.prompt}")
        click.echo(f"Description: {task.description or '-'}")
        click.echo(f"Enabled:     {'yes' if task.enabled else 'no'}")
        if task.cron_expression:
            click.echo(f"Schedule:    cron '{task.cron_expression}'")
        elif task.fire_at:
            click.echo(f"Schedule:    at {_format_datetime(task.fire_at)}")
        click.echo(f"Created:     {_format_datetime(task.created_at)}")
        click.echo(f"Last run:    {_format_datetime(task.last_run_at)}")
        click.echo(f"Next run:    {_format_datetime(task.next_run_at)}")
        if task.last_error:
            click.echo(f"Last error:  {task.last_error}")

    asyncio.run(_show())


@schedule.command(name="run")
@click.argument("task_id")
@click.pass_context
def schedule_run(ctx: click.Context, task_id: str) -> None:
    """Manually trigger a scheduled task."""
    app: CliAppContext = ctx.obj["app"]
    app.confirm_callback = CliConfirmHandler()

    async def _run() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        # Verify task exists
        task = await store.get_task(task_id)
        if task is None:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        # Create orchestrator
        orchestrator = app.make_orchestrator()

        # Build scheduler just for this one run
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

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(app.inference.close())


@schedule.command(name="enable")
@click.argument("task_id")
@click.pass_context
def schedule_enable(ctx: click.Context, task_id: str) -> None:
    """Enable a scheduled task."""
    app: CliAppContext = ctx.obj["app"]

    async def _enable() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        success = await store.set_enabled(task_id, True)
        if not success:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)
        click.echo(f"Task {task_id} enabled")

    asyncio.run(_enable())


@schedule.command(name="disable")
@click.argument("task_id")
@click.pass_context
def schedule_disable(ctx: click.Context, task_id: str) -> None:
    """Disable a scheduled task."""
    app: CliAppContext = ctx.obj["app"]

    async def _disable() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        success = await store.disable_task(task_id)

        if not success:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        click.echo(f"Task {task_id} disabled")

    asyncio.run(_disable())


@schedule.command(name="remove")
@click.argument("task_id")
@click.pass_context
def schedule_remove(ctx: click.Context, task_id: str) -> None:
    """Remove a scheduled task."""
    app: CliAppContext = ctx.obj["app"]

    async def _remove() -> None:
        await app.bootstrap_db()
        store = _require_scheduler_store(app)

        success = await store.delete_task(task_id)
        if not success:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)
        click.echo(f"Task {task_id} removed")

    asyncio.run(_remove())


@schedule.command(name="daemon")
@click.option(
    "--tick-interval",
    type=float,
    default=None,
    help="Tick interval in seconds (default: from config)",
)
@click.pass_context
def schedule_daemon(ctx: click.Context, tick_interval: float | None) -> None:
    """Run the scheduler daemon (blocks until Ctrl-C)."""
    # Headless daemon — no confirmation callback. Tools requiring confirmation
    # will be denied, which is correct for unattended execution.
    ctx.obj["confirm_callback"] = None
    cfg: HestiaConfig = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    session_store: SessionStore = ctx.obj["session_store"]
    inference: InferenceClient = ctx.obj["inference"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]
    failure_store: FailureStore = ctx.obj["failure_store"]
    trace_store: TraceStore = ctx.obj["trace_store"]

    # Use config tick interval if not specified via CLI
    tick = tick_interval if tick_interval is not None else cfg.scheduler.tick_interval_seconds

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[scheduler:{task.id}] {text}")

    scanner = InjectionScanner(
        enabled=cfg.security.injection_scanner_enabled,
        entropy_threshold=cfg.security.injection_entropy_threshold,
    )

    async def _daemon() -> None:
        await _bootstrap_db(db, memory_store, failure_store, trace_store)

        scheduler_store = SchedulerStore(db)

        # Headless: no stdin confirmation (matches ctx.obj["confirm_callback"] = None above)
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=None,
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
            failure_store=failure_store,
            trace_store=trace_store,
            injection_scanner=scanner,
        )

        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=orchestrator,
            response_callback=response_callback,
            tick_interval_seconds=tick,
        )

        await scheduler.start()
        click.echo(f"Scheduler daemon started (tick={tick}s). Press Ctrl-C to stop.")

        try:
            # Wait forever until interrupted
            while True:
                await asyncio.sleep(1)
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
            # Cancel the main task
            main_task.cancel()
            try:
                loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                pass
        finally:
            loop.run_until_complete(inference.close())
            loop.close()

    run_daemon()


@cli.command(name="telegram")
@click.pass_context
def run_telegram(ctx: click.Context) -> None:
    """Run Hestia as a Telegram bot (blocks until Ctrl-C)."""
    ctx.obj["confirm_callback"] = None
    cfg: HestiaConfig = ctx.obj["config"]
    if not cfg.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]
    failure_store: FailureStore = ctx.obj["failure_store"]
    trace_store: TraceStore = ctx.obj["trace_store"]

    scanner = InjectionScanner(
        enabled=cfg.security.injection_scanner_enabled,
        entropy_threshold=cfg.security.injection_entropy_threshold,
    )

    if not cfg.telegram.bot_token:
        click.echo("Error: telegram.bot_token is required in config.", err=True)
        click.echo("Set it in your config file or via environment.", err=True)
        sys.exit(1)

    from hestia.platforms.telegram_adapter import TelegramAdapter

    def _make_telegram_scheduler_callback(
        adapter: TelegramAdapter, session_store: SessionStore
    ) -> Callable[[ScheduledTask, str], Coroutine[Any, Any, None]]:
        """Create a scheduler response callback that routes to Telegram."""

        async def callback(task: ScheduledTask, text: str) -> None:
            session = await session_store.get_session(task.session_id)
            if session is None or session.platform != "telegram":
                logger.warning("Scheduler task %s: session not found or not telegram", task.id)
                return
            await adapter.send_message(session.platform_user, text)

        return callback

    async def _run() -> None:
        await _bootstrap_db(db, memory_store, failure_store, trace_store)

        adapter = TelegramAdapter(cfg.telegram)

        current_telegram_user: ContextVar[str] = ContextVar(
            "current_telegram_user", default=""
        )

        async def _telegram_confirm_callback(
            tool_name: str, arguments: dict[str, object]
        ) -> bool:
            """Async confirmation callback wired to Telegram inline keyboard."""
            platform_user = current_telegram_user.get()
            if not platform_user:
                logger.warning(
                    "Telegram confirmation requested without bound platform_user; denying tool '%s'",
                    tool_name,
                )
                return False
            return await adapter.request_confirmation(platform_user, tool_name, arguments)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=_telegram_confirm_callback,
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
            failure_store=failure_store,
            trace_store=trace_store,
            injection_scanner=scanner,
        )

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        # Session cache: telegram_user_id -> Session
        user_sessions: dict[str, Session] = {}

        async def on_message(platform_name: str, platform_user: str, text: str) -> None:
            """Handle incoming Telegram message."""
            token = current_telegram_user.set(platform_user)
            # Get or create session for this user (DB-backed, survives restarts)
            try:
                if platform_user not in user_sessions:
                    session = await session_store.get_or_create_session(
                        "telegram", platform_user
                    )
                    user_sessions[platform_user] = session
                else:
                    session = user_sessions[platform_user]

                user_message = Message(role="user", content=text)

                async def respond(response_text: str) -> None:
                    await adapter.send_message(platform_user, response_text)

                await orchestrator.process_turn(
                    session=session,
                    user_message=user_message,
                    respond_callback=respond,
                    system_prompt=cfg.system_prompt,
                    platform=adapter,
                    platform_user=platform_user,
                )
            except Exception as e:  # Outermost boundary — intentionally broad
                logger.exception("Turn failed for user %s", platform_user)
                await adapter.send_error(platform_user, f"Turn failed: {e}")
            finally:
                current_telegram_user.reset(token)

        await adapter.start(on_message)
        click.echo("Telegram bot started. Press Ctrl-C to stop.")

        # Also start the scheduler
        scheduler_store = SchedulerStore(db)
        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=orchestrator,
            response_callback=_make_telegram_scheduler_callback(adapter, session_store),
            tick_interval_seconds=cfg.scheduler.tick_interval_seconds,
        )
        await scheduler.start()

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await scheduler.stop()
            await adapter.stop()
            await inference.close()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\nShutting down.")


@cli.command(name="matrix")
@click.pass_context
def run_matrix(ctx: click.Context) -> None:
    """Run Hestia as a Matrix bot (blocks until Ctrl-C)."""
    ctx.obj["confirm_callback"] = None
    cfg: HestiaConfig = ctx.obj["config"]
    if not cfg.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]
    failure_store: FailureStore = ctx.obj["failure_store"]
    trace_store: TraceStore = ctx.obj["trace_store"]

    scanner = InjectionScanner(
        enabled=cfg.security.injection_scanner_enabled,
        entropy_threshold=cfg.security.injection_entropy_threshold,
    )

    if not cfg.matrix.access_token:
        click.echo("Error: matrix.access_token is required in config.", err=True)
        click.echo("Set it in your config file or via environment.", err=True)
        sys.exit(1)

    if not cfg.matrix.user_id:
        click.echo("Error: matrix.user_id is required in config.", err=True)
        sys.exit(1)

    from hestia.platforms.matrix_adapter import MatrixAdapter

    def _make_matrix_scheduler_callback(
        adapter: MatrixAdapter, session_store: SessionStore
    ) -> Callable[[ScheduledTask, str], Coroutine[Any, Any, None]]:
        """Create a scheduler response callback that routes to Matrix."""

        async def callback(task: ScheduledTask, text: str) -> None:
            session = await session_store.get_session(task.session_id)
            if session is None or session.platform != "matrix":
                logger.warning("Scheduler task %s: session not found or not matrix", task.id)
                return
            await adapter.send_message(session.platform_user, text)

        return callback

    async def _run() -> None:
        await _bootstrap_db(db, memory_store, failure_store, trace_store)

        adapter = MatrixAdapter(cfg.matrix)

        current_matrix_room: ContextVar[str] = ContextVar("current_matrix_room", default="")

        async def _matrix_confirm_callback(
            tool_name: str, arguments: dict[str, object]
        ) -> bool:
            """Async confirmation callback wired to Matrix reply pattern."""
            room_id = current_matrix_room.get()
            if not room_id:
                logger.warning(
                    "Matrix confirmation requested without bound room_id; denying tool '%s'",
                    tool_name,
                )
                return False
            return await adapter.request_confirmation(room_id, tool_name, arguments)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=_matrix_confirm_callback,
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
            failure_store=failure_store,
            trace_store=trace_store,
            injection_scanner=scanner,
        )

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        # Session cache: room_id -> Session
        room_sessions: dict[str, Session] = {}

        async def on_message(platform_name: str, platform_user: str, text: str) -> None:
            """Handle incoming Matrix message."""
            token = current_matrix_room.set(platform_user)
            # Get or create session for this room (DB-backed, survives restarts)
            try:
                if platform_user not in room_sessions:
                    session = await session_store.get_or_create_session(
                        "matrix", platform_user
                    )
                    room_sessions[platform_user] = session
                else:
                    session = room_sessions[platform_user]

                user_message = Message(role="user", content=text)

                async def respond(response_text: str) -> None:
                    await adapter.send_message(platform_user, response_text)

                await orchestrator.process_turn(
                    session=session,
                    user_message=user_message,
                    respond_callback=respond,
                    system_prompt=cfg.system_prompt,
                    platform=adapter,
                    platform_user=platform_user,
                )
            except Exception as e:  # Outermost boundary — intentionally broad
                logger.exception("Turn failed for room %s", platform_user)
                await adapter.send_error(platform_user, f"Turn failed: {e}")
            finally:
                current_matrix_room.reset(token)

        await adapter.start(on_message)
        click.echo("Matrix bot started. Press Ctrl-C to stop.")

        # Also start the scheduler
        scheduler_store = SchedulerStore(db)
        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=orchestrator,
            response_callback=_make_matrix_scheduler_callback(adapter, session_store),
            tick_interval_seconds=cfg.scheduler.tick_interval_seconds,
        )
        await scheduler.start()

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await scheduler.stop()
            await adapter.stop()
            await inference.close()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\nShutting down.")


@cli.group()
@click.pass_context
def memory(ctx: click.Context) -> None:
    """Manage long-term memory."""
    pass


@memory.command(name="search")
@click.argument("query")
@click.option("--limit", type=int, default=5)
@click.pass_context
def memory_search(ctx: click.Context, query: str, limit: int) -> None:
    """Search memories."""
    app: CliAppContext = ctx.obj["app"]

    async def _search() -> None:
        await app.bootstrap_db()

        results = await app.memory_store.search(query, limit=limit)
        if not results:
            click.echo("No memories found.")
            return

        for mem in results:
            tags = f" [{mem.tags}]" if mem.tags else ""
            date = mem.created_at.strftime("%Y-%m-%d %H:%M")
            click.echo(f"{mem.id}  {date}{tags}  {mem.content}")

    asyncio.run(_search())


@memory.command(name="list")
@click.option("--tag", default=None)
@click.option("--limit", type=int, default=20)
@click.pass_context
def memory_list(ctx: click.Context, tag: str | None, limit: int) -> None:
    """List recent memories."""
    app: CliAppContext = ctx.obj["app"]

    async def _list() -> None:
        await app.bootstrap_db()

        results = await app.memory_store.list_memories(tag=tag, limit=limit)
        if not results:
            click.echo("No memories found.")
            return

        for mem in results:
            tags = f" [{mem.tags}]" if mem.tags else ""
            date = mem.created_at.strftime("%Y-%m-%d %H:%M")
            click.echo(f"{mem.id}  {date}{tags}  {mem.content}")

    asyncio.run(_list())


@memory.command(name="add")
@click.argument("content")
@click.option("--tags", default="")
@click.pass_context
def memory_add(ctx: click.Context, content: str, tags: str) -> None:
    """Add a memory manually."""
    app: CliAppContext = ctx.obj["app"]

    async def _add() -> None:
        await app.bootstrap_db()

        tag_list = tags.split() if tags else []
        mem = await app.memory_store.save(content=content, tags=tag_list)
        click.echo(f"Saved: {mem.id}")

    asyncio.run(_add())


@memory.command(name="remove")
@click.argument("memory_id")
@click.pass_context
def memory_remove(ctx: click.Context, memory_id: str) -> None:
    """Delete a memory by ID."""
    app: CliAppContext = ctx.obj["app"]

    async def _remove() -> None:
        await app.bootstrap_db()

        success = await app.memory_store.delete(memory_id)
        if not success:
            click.echo(f"Memory not found: {memory_id}", err=True)
            sys.exit(1)
        click.echo(f"Deleted: {memory_id}")

    asyncio.run(_remove())


# Skill command group
@cli.group()
@click.pass_context
def skill(ctx: click.Context) -> None:
    """Manage skills."""
    pass


@skill.command(name="list")
@click.option("--state", "state_filter", default=None, help="Filter by state (draft, tested, trusted, deprecated, disabled)")
@click.option("--all", "show_all", is_flag=True, help="Include disabled skills")
@click.pass_context
def skill_list(ctx: click.Context, state_filter: str | None, show_all: bool) -> None:
    """List skills with their states."""
    app: CliAppContext = ctx.obj["app"]

    async def _list() -> None:
        await app.bootstrap_db()
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

    asyncio.run(_list())


@skill.command(name="show")
@click.argument("name")
@click.pass_context
def skill_show(ctx: click.Context, name: str) -> None:
    """Show skill details."""
    app: CliAppContext = ctx.obj["app"]

    async def _show() -> None:
        await app.bootstrap_db()
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

    asyncio.run(_show())


@skill.command(name="promote")
@click.argument("name")
@click.pass_context
def skill_promote(ctx: click.Context, name: str) -> None:
    """Advance skill state (draft -> tested -> trusted)."""
    app: CliAppContext = ctx.obj["app"]

    async def _promote() -> None:
        await app.bootstrap_db()
        if app.skill_store is None:
            click.echo("Skill store not available", err=True)
            sys.exit(1)

        record = await app.skill_store.get_by_name(name)
        if record is None:
            click.echo(f"Skill not found: {name}", err=True)
            sys.exit(1)

        # State transitions
        transitions = {
            SkillState.DRAFT: SkillState.TESTED,
            SkillState.TESTED: SkillState.TRUSTED,
            SkillState.TRUSTED: SkillState.TRUSTED,  # Already at max
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

    asyncio.run(_promote())


@skill.command(name="demote")
@click.argument("name")
@click.pass_context
def skill_demote(ctx: click.Context, name: str) -> None:
    """Move skill back one state."""
    app: CliAppContext = ctx.obj["app"]

    async def _demote() -> None:
        await app.bootstrap_db()
        if app.skill_store is None:
            click.echo("Skill store not available", err=True)
            sys.exit(1)

        record = await app.skill_store.get_by_name(name)
        if record is None:
            click.echo(f"Skill not found: {name}", err=True)
            sys.exit(1)

        # State transitions (reverse)
        transitions = {
            SkillState.DRAFT: SkillState.DISABLED,
            SkillState.TESTED: SkillState.DRAFT,
            SkillState.TRUSTED: SkillState.TESTED,
            SkillState.DEPRECATED: SkillState.DEPRECATED,  # Keep deprecated
            SkillState.DISABLED: SkillState.DISABLED,  # Already at min
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

    asyncio.run(_demote())


@skill.command(name="disable")
@click.argument("name")
@click.pass_context
def skill_disable(ctx: click.Context, name: str) -> None:
    """Disable a skill without removing it."""
    app: CliAppContext = ctx.obj["app"]

    async def _disable() -> None:
        await app.bootstrap_db()
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

    asyncio.run(_disable())


@skill.command(name="test")
@click.argument("name")
@click.pass_context
def skill_test(ctx: click.Context, name: str) -> None:
    """Run skill in sandbox mode (not yet implemented)."""
    click.echo(f"Skill testing not yet implemented for: {name}")
    click.echo("Note: Run the skill manually and observe results.")


class AuditGroup(click.Group):
    """Custom group that defaults to 'run' when no subcommand is given."""

    def invoke(self, ctx: click.Context) -> Any:
        if ctx.protected_args:
            return super().invoke(ctx)
        ctx.invoked_subcommand = "run"
        return self.commands["run"].invoke(ctx)


@cli.group(name="audit", cls=AuditGroup)
@click.pass_context
def audit_group(ctx: click.Context) -> None:
    """Security audit commands."""
    pass


@audit_group.command(name="run")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
@click.pass_context
def audit_run(ctx: click.Context, output_json: bool, output: str | None) -> None:
    """Run security audit checks."""
    from hestia.audit import SecurityAuditor

    app: CliAppContext = ctx.obj["app"]

    async def _audit() -> None:
        await app.bootstrap_db()

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

        # Exit with error code if critical findings
        critical_count = sum(1 for f in report.findings if f.severity == "critical")
        if critical_count > 0:
            sys.exit(1)

    asyncio.run(_audit())


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


@audit_group.command(name="egress")
@click.option("--since", default="7d", help="Time window (e.g. 7d, 24h, 30d)")
@click.pass_context
def audit_egress(ctx: click.Context, since: str) -> None:
    """Print domain-level egress aggregation."""
    app: CliAppContext = ctx.obj["app"]

    async def _egress() -> None:
        await app.bootstrap_db()

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
            # first-time-this-week heuristic: if the earliest record for this domain
            # is within the window, flag it. We approximate by checking if overall
            # count is low (same as <3) since we don't have historical baseline.
            click.echo(f"{domain:<40} {total:>10} {failures:>10} {anomaly}")

    asyncio.run(_egress())


# ------------------------------------------------------------------
# Email CLI
# ------------------------------------------------------------------

@cli.group()
@click.pass_context
def email(ctx: click.Context) -> None:
    """Email integration commands."""
    pass


@email.command(name="check")
@click.pass_context
def email_check(ctx: click.Context) -> None:
    """Check email connectivity (IMAP login test)."""
    app: CliAppContext = ctx.obj["app"]
    cfg = app.config

    if not cfg.email.imap_host:
        click.echo("Email is not configured. Set email.imap_host in your config.", err=True)
        sys.exit(1)

    from hestia.email.adapter import EmailAdapter

    async def _check() -> None:
        adapter = EmailAdapter(cfg.email)
        try:
            messages = await adapter.list_messages(limit=1)
        except Exception as exc:
            click.echo(f"Email check failed: {type(exc).__name__}: {exc}", err=True)
            sys.exit(1)
        click.echo(f"IMAP connection OK ({cfg.email.imap_host}:{cfg.email.imap_port})")
        click.echo(f"Default folder: {cfg.email.default_folder}")
        click.echo(f"Messages found: {len(messages)}")

    asyncio.run(_check())


@email.command(name="list")
@click.option("--folder", default="INBOX", help="IMAP folder")
@click.option("--limit", default=5, help="Max messages")
@click.option("--unread-only", is_flag=True, default=False)
@click.pass_context
def email_list_cmd(
    ctx: click.Context, folder: str, limit: int, unread_only: bool
) -> None:
    """List recent emails."""
    app: CliAppContext = ctx.obj["app"]
    cfg = app.config

    if not cfg.email.imap_host:
        click.echo("Email is not configured.", err=True)
        sys.exit(1)

    from hestia.email.adapter import EmailAdapter

    async def _list() -> None:
        adapter = EmailAdapter(cfg.email)
        try:
            messages = await adapter.list_messages(
                folder=folder, limit=limit, unread_only=unread_only
            )
        except Exception as exc:
            click.echo(f"Failed: {type(exc).__name__}: {exc}", err=True)
            sys.exit(1)
        if not messages:
            click.echo("No messages found.")
            return
        for m in messages:
            click.echo(
                f"[{m['message_id']}] {m['from']} | {m['subject']} | {m['date']}"
            )

    asyncio.run(_list())


@email.command(name="read")
@click.argument("message_id")
@click.pass_context
def email_read_cmd(ctx: click.Context, message_id: str) -> None:
    """Read a single email by IMAP UID."""
    app: CliAppContext = ctx.obj["app"]
    cfg = app.config

    if not cfg.email.imap_host:
        click.echo("Email is not configured.", err=True)
        sys.exit(1)

    from hestia.email.adapter import EmailAdapter

    async def _read() -> None:
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

    asyncio.run(_read())


@cli.group()
@click.pass_context
def policy(ctx: click.Context) -> None:
    """Manage and view security policies."""
    pass


@policy.command(name="show")
@click.pass_context
def policy_show(ctx: click.Context) -> None:
    """Show current effective policy configuration."""

    from hestia.core.types import Session, SessionState, SessionTemperature
    from hestia.tools.capabilities import (
        EMAIL_SEND,
        MEMORY_READ,
        MEMORY_WRITE,
        NETWORK_EGRESS,
        SHELL_EXEC,
        WRITE_LOCAL,
    )

    app: CliAppContext = ctx.obj["app"]

    async def _show() -> None:
        await app.bootstrap_db()

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

        # Tool filtering by session type
        # Trust profile
        click.echo("-" * 40)
        click.echo("TRUST PROFILE")
        click.echo("-" * 40)
        click.echo(f"  auto_approve_tools: {cfg.trust.auto_approve_tools or '(none)'}")
        click.echo(f"  scheduler_shell_exec: {cfg.trust.scheduler_shell_exec}")
        click.echo(f"  scheduler_email_send: {cfg.trust.scheduler_email_send}")
        click.echo(f"  subagent_shell_exec: {cfg.trust.subagent_shell_exec}")
        click.echo(f"  subagent_write_local: {cfg.trust.subagent_write_local}")
        click.echo(f"  subagent_email_send: {cfg.trust.subagent_email_send}")
        click.echo("")

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
                # Show why each tool is blocked
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
        click.echo("    - Keywords: delegate, subagent, spawn task, background task")
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
        click.echo("  Tools requiring confirmation (interactive only):")
        click.echo("    - write_file")
        click.echo("    - terminal (for destructive operations)")
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
        click.echo("  Max attempts: 2")
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

    asyncio.run(_show())


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
