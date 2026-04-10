"""CLI adapter for Hestia - local-first LLM agent framework."""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

import click

from hestia.artifacts.store import ArtifactStore
from hestia.config import HestiaConfig
from hestia.context.builder import ContextBuilder
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, ScheduledTask, Session
from hestia.inference import SlotManager
from hestia.orchestrator import Orchestrator
from hestia.persistence.db import Database
from hestia.persistence.scheduler import SchedulerStore
from hestia.persistence.sessions import SessionStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.scheduler import Scheduler
from hestia.memory.store import MemoryStore
from hestia.tools.builtin import (
    current_time,
    http_get,
    list_dir,
    make_delegate_task_tool,
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
    read_file,
    terminal,
    write_file,
)
from hestia.tools.registry import ToolRegistry

# Path to calibration file (not configurable via CLI)
DEFAULT_CALIBRATION_PATH = Path("docs/calibration.json")


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

    async def __call__(self, tool_name: str, arguments: dict) -> bool:
        """Prompt user for confirmation."""
        click.echo(f"\nTool call requested: {tool_name}")
        click.echo(f"Arguments: {arguments}")
        return click.confirm("Execute?", default=True)


async def _handle_meta_command(
    cmd: str,
    session: Session,
    session_store: SessionStore,
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
        return False, new_session

    click.echo(f"Unknown command: {cmd}. Type /help for a list.")
    return False, session


@click.group()
@click.option("--config", "config_path", type=click.Path(exists=True), default=None,
              help="Path to Hestia config file (Python)")
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

    # Build subsystems from config
    db = Database(cfg.storage.database_url)
    artifact_store = ArtifactStore(cfg.storage.artifacts_dir)
    inference = InferenceClient(cfg.inference.base_url, cfg.inference.model_name)
    session_store = SessionStore(db)
    policy = DefaultPolicyEngine()

    # Context builder with calibration
    calibration_path = Path("docs/calibration.json")
    context_builder = ContextBuilder.from_calibration_file(
        inference, policy, calibration_path
    )

    # Memory store for long-term memory
    memory_store = MemoryStore(db)

    # Tool registry with built-in tools
    tool_registry = ToolRegistry(artifact_store)
    tool_registry.register(current_time)
    tool_registry.register(http_get)
    tool_registry.register(list_dir)
    tool_registry.register(read_file)
    tool_registry.register(terminal)
    tool_registry.register(write_file)

    # Register memory tools (bound to the memory store instance)
    tool_registry.register(make_search_memory_tool(memory_store))
    tool_registry.register(make_save_memory_tool(memory_store))
    tool_registry.register(make_list_memories_tool(memory_store))

    # Slot manager for KV-cache persistence
    slot_manager = SlotManager(
        inference=inference,
        session_store=session_store,
        slot_dir=cfg.slots.slot_dir,
        pool_size=cfg.slots.pool_size,
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
        )

    tool_registry.register(make_delegate_task_tool(session_store, orchestrator_factory))

    # Store in context
    ctx.obj["config"] = cfg
    ctx.obj["db"] = db
    ctx.obj["inference"] = inference
    ctx.obj["session_store"] = session_store
    ctx.obj["context_builder"] = context_builder
    ctx.obj["tool_registry"] = tool_registry
    ctx.obj["policy"] = policy
    ctx.obj["slot_manager"] = slot_manager
    ctx.obj["memory_store"] = memory_store
    ctx.obj["verbose"] = cfg.verbose


async def _bootstrap_db(db: Database, memory_store: MemoryStore) -> None:
    """Bootstrap database and FTS table for CLI commands.

    Repeated in many commands because Click callback + async don't mix cleanly.
    Each command extracts its own ctx.obj refs and calls this helper.
    """
    await db.connect()
    await db.create_tables()
    await memory_store.create_table()


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize database, artifacts, and slot directories."""
    cfg: HestiaConfig = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _init() -> None:
        await _bootstrap_db(db, memory_store)
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
    ctx.obj["confirm_callback"] = CliConfirmHandler()
    cfg: HestiaConfig = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]
    verbose: bool = ctx.obj["verbose"]

    async def _chat() -> None:
        await _bootstrap_db(db, memory_store)

        # Create orchestrator (headless — no confirmation)
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=None,
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
        )

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        # Get or create session for CLI user
        session = await session_store.get_or_create_session("cli", "default")
        click.echo(f"Session: {session.id}")
        click.echo("Type 'exit' or 'quit' to end the session, or /help for commands.\n")

        response_handler = CliResponseHandler(verbose=verbose)

        while True:
            try:
                user_input = click.prompt("You", type=str).strip()
                if user_input.lower() in ("exit", "quit"):
                    break
                if user_input.startswith("/"):
                    should_exit, session = await _handle_meta_command(
                        user_input, session, session_store
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
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                if verbose:
                    import traceback

                    traceback.print_exc()

        click.echo("Goodbye!")

    try:
        asyncio.run(_chat())
    finally:
        asyncio.run(inference.close())


@cli.command()
@click.argument("message")
@click.pass_context
def ask(ctx: click.Context, message: str) -> None:
    """Send a single message and get a response."""
    ctx.obj["confirm_callback"] = CliConfirmHandler()
    cfg: HestiaConfig = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]
    verbose: bool = ctx.obj["verbose"]

    async def _ask() -> None:
        await _bootstrap_db(db, memory_store)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
        )

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        session = await session_store.get_or_create_session("cli", "default")

        user_message = Message(role="user", content=message)

        response_handler = CliResponseHandler(verbose=verbose)

        await orchestrator.process_turn(
            session=session,
            user_message=user_message,
            respond_callback=response_handler,
        )

    try:
        asyncio.run(_ask())
    finally:
        asyncio.run(inference.close())


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check inference server health."""
    inference: InferenceClient = ctx.obj["inference"]

    async def _health() -> None:
        try:
            health_info = await inference.health()
            click.echo("Inference server is healthy:")
            for key, value in health_info.items():
                click.echo(f"  {key}: {value}")
        except Exception as e:
            click.echo(f"Health check failed: {e}", err=True)
            sys.exit(1)
        finally:
            await inference.close()

    asyncio.run(_health())


# Schedule command group
@cli.group()
def schedule() -> None:
    """Manage scheduled tasks."""
    pass


@schedule.command(name="add")
@click.option("--cron", help="Cron expression (e.g., '0 9 * * 1-5' for weekdays at 9am)")
@click.option("--at", "fire_at_str", help="One-shot time (ISO format: 2026-04-15T15:00:00)")
@click.option("--description", "-d", help="Task description")
@click.argument("prompt")
@click.pass_context
def schedule_add(
    ctx: click.Context,
    cron: str | None,
    fire_at_str: str | None,
    description: str | None,
    prompt: str,
) -> None:
    """Add a scheduled task."""
    db: Database = ctx.obj["db"]
    session_store: SessionStore = ctx.obj["session_store"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    # Validate exactly one of cron or fire_at
    if cron is not None and fire_at_str is not None:
        click.echo("Error: Cannot specify both --cron and --at", err=True)
        sys.exit(1)
    if cron is None and fire_at_str is None:
        click.echo("Error: Must specify either --cron or --at", err=True)
        sys.exit(1)

    # Parse fire_at if provided
    fire_at: datetime | None = None
    if fire_at_str is not None:
        try:
            fire_at = datetime.fromisoformat(fire_at_str)
        except ValueError:
            click.echo(f"Error: Invalid datetime format '{fire_at_str}'. Use ISO format: 2026-04-15T15:00:00", err=True)
            sys.exit(1)

        # Reject past times
        if fire_at < datetime.now():
            click.echo(f"Error: Cannot schedule task in the past: {fire_at}", err=True)
            sys.exit(1)

    async def _add() -> None:
        await _bootstrap_db(db, memory_store)

        # Get or create default CLI session
        session = await session_store.get_or_create_session("cli", "default")
        if session is None:
            click.echo("Warning: No active session exists. Creating one.", err=True)

        scheduler_store = SchedulerStore(db)

        try:
            task = await scheduler_store.create_task(
                session_id=session.id,
                prompt=prompt,
                description=description,
                cron_expression=cron,
                fire_at=fire_at,
            )
            click.echo(f"Created task: {task.id}")
            if task.cron_expression:
                click.echo(f"  Schedule: cron '{task.cron_expression}'")
            elif task.fire_at:
                click.echo(f"  Schedule: at {task.fire_at}")
            click.echo(f"  Next run: {task.next_run_at}")
        except Exception as e:
            click.echo(f"Error creating task: {e}", err=True)
            sys.exit(1)

    asyncio.run(_add())


@schedule.command(name="list")
@click.pass_context
def schedule_list(ctx: click.Context) -> None:
    """List scheduled tasks."""
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _list() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)
        tasks = await scheduler_store.list_tasks_for_session(
            session_id=None, include_disabled=True
        )

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
                sched = f"at: {task.fire_at.strftime('%Y-%m-%d %H:%M')[:16]}"
            else:
                sched = "unknown"
            enabled = "yes" if task.enabled else "no"
            next_run = task.next_run_at.strftime("%Y-%m-%d %H:%M") if task.next_run_at else "-"
            click.echo(f"{task.id:<20} {desc:<25} {sched:<20} {enabled:<8} {next_run}")

    asyncio.run(_list())


@schedule.command(name="show")
@click.argument("task_id")
@click.pass_context
def schedule_show(ctx: click.Context, task_id: str) -> None:
    """Show details of a scheduled task."""
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _show() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)
        task = await scheduler_store.get_task(task_id)

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
            click.echo(f"Schedule:    at {task.fire_at}")
        click.echo(f"Created:     {task.created_at}")
        click.echo(f"Last run:    {task.last_run_at or '-'}")
        click.echo(f"Next run:    {task.next_run_at or '-'}")
        if task.last_error:
            click.echo(f"Last error:  {task.last_error}")

    asyncio.run(_show())


@schedule.command(name="run")
@click.argument("task_id")
@click.pass_context
def schedule_run(ctx: click.Context, task_id: str) -> None:
    """Manually trigger a scheduled task."""
    ctx.obj["confirm_callback"] = CliConfirmHandler()
    cfg: HestiaConfig = ctx.obj["config"]
    db: Database = ctx.obj["db"]
    session_store: SessionStore = ctx.obj["session_store"]
    inference: InferenceClient = ctx.obj["inference"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]
    verbose: bool = ctx.obj["verbose"]

    async def _run() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)

        # Verify task exists
        task = await scheduler_store.get_task(task_id)
        if task is None:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)

        # Create orchestrator
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
        )

        # Build scheduler just for this one run
        async def response_callback(task: ScheduledTask, text: str) -> None:
            click.echo(f"[{task.id}] {text}")

        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=orchestrator,
            response_callback=response_callback,
        )

        try:
            await scheduler.run_now(task_id)
            click.echo(f"Task {task_id} executed successfully")
        except Exception as e:
            click.echo(f"Error running task: {e}", err=True)
            sys.exit(1)

    try:
        asyncio.run(_run())
    finally:
        asyncio.run(inference.close())


@schedule.command(name="enable")
@click.argument("task_id")
@click.pass_context
def schedule_enable(ctx: click.Context, task_id: str) -> None:
    """Enable a scheduled task."""
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _enable() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)
        success = await scheduler_store.set_enabled(task_id, True)
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
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _disable() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)
        success = await scheduler_store.disable_task(task_id)

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
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _remove() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)
        success = await scheduler_store.delete_task(task_id)
        if not success:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)
        click.echo(f"Task {task_id} removed")

    asyncio.run(_remove())


@schedule.command(name="daemon")
@click.option("--tick-interval", type=float, default=None,
              help="Tick interval in seconds (default: from config)")
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

    # Use config tick interval if not specified via CLI
    tick = tick_interval if tick_interval is not None else cfg.scheduler.tick_interval_seconds

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[scheduler:{task.id}] {text}")

    async def _daemon() -> None:
        await _bootstrap_db(db, memory_store)

        scheduler_store = SchedulerStore(db)

        # Create orchestrator
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
        )

        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=orchestrator,
            response_callback=response_callback,
            tick_interval_seconds=tick,
        )

        await scheduler.start()
        click.echo(f"Scheduler daemon started (tick={tick_interval}s). Press Ctrl-C to stop.")

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
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    if not cfg.telegram.bot_token:
        click.echo("Error: telegram.bot_token is required in config.", err=True)
        click.echo("Set it in your config file or via environment.", err=True)
        sys.exit(1)

    from hestia.platforms.telegram_adapter import TelegramAdapter

    def _make_telegram_scheduler_callback(
        adapter: TelegramAdapter, session_store: SessionStore
    ):
        """Create a scheduler response callback that routes to Telegram."""
        async def callback(task: ScheduledTask, text: str) -> None:
            session = await session_store.get_session(task.session_id)
            if session is None or session.platform != "telegram":
                logger.warning(
                    "Scheduler task %s: session not found or not telegram", task.id
                )
                return
            await adapter.send_message(session.platform_user, text)
        return callback

    async def _run() -> None:
        await _bootstrap_db(db, memory_store)

        adapter = TelegramAdapter(cfg.telegram)

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            max_iterations=cfg.max_iterations,
            slot_manager=slot_manager,
            # No confirm_callback for Telegram — tools requiring confirmation
            # (e.g., write_file) will refuse to run and tell the model why.
            # TODO: Implement confirmation via Telegram inline keyboard buttons.
        )

        # Recover stale turns from previous crash
        recovered = await orchestrator.recover_stale_turns()
        if recovered:
            click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

        # Session cache: telegram_user_id -> Session
        user_sessions: dict[str, Session] = {}

        async def on_message(platform_name: str, platform_user: str, text: str) -> None:
            """Handle incoming Telegram message."""
            # Get or create session for this user (DB-backed, survives restarts)
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

            try:
                await orchestrator.process_turn(
                    session=session,
                    user_message=user_message,
                    respond_callback=respond,
                    system_prompt=cfg.system_prompt,
                    platform=adapter,
                    platform_user=platform_user,
                )
            except Exception as e:
                logger.exception("Turn failed for user %s", platform_user)
                await adapter.send_error(platform_user, f"Turn failed: {e}")

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
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _search() -> None:
        await _bootstrap_db(db, memory_store)

        results = await memory_store.search(query, limit=limit)
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
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _list() -> None:
        await _bootstrap_db(db, memory_store)

        results = await memory_store.list_memories(tag=tag, limit=limit)
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
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _add() -> None:
        await _bootstrap_db(db, memory_store)

        tag_list = tags.split() if tags else []
        mem = await memory_store.save(content=content, tags=tag_list)
        click.echo(f"Saved: {mem.id}")

    asyncio.run(_add())


@memory.command(name="remove")
@click.argument("memory_id")
@click.pass_context
def memory_remove(ctx: click.Context, memory_id: str) -> None:
    """Delete a memory by ID."""
    db: Database = ctx.obj["db"]
    memory_store: MemoryStore = ctx.obj["memory_store"]

    async def _remove() -> None:
        await _bootstrap_db(db, memory_store)

        success = await memory_store.delete(memory_id)
        if not success:
            click.echo(f"Memory not found: {memory_id}", err=True)
            sys.exit(1)
        click.echo(f"Deleted: {memory_id}")

    asyncio.run(_remove())


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
