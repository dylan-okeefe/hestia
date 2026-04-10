"""CLI adapter for Hestia - local-first LLM agent framework."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import click

from hestia.artifacts.store import ArtifactStore
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
from hestia.tools.builtin import current_time, read_file, terminal
from hestia.tools.registry import ToolRegistry

# Default configuration
DEFAULT_DB_PATH = Path("hestia.db")
DEFAULT_ARTIFACTS_PATH = Path("artifacts")
DEFAULT_SLOT_DIR = Path("slots")
DEFAULT_SLOT_POOL_SIZE = 4
DEFAULT_CALIBRATION_PATH = Path("docs/calibration.json")
DEFAULT_INFERENCE_URL = "http://localhost:8001"
DEFAULT_MODEL = "Qwen3.5-9B-UD-Q4_K_XL.gguf"


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
@click.option("--db-path", type=click.Path(), default=DEFAULT_DB_PATH)
@click.option("--artifacts-path", type=click.Path(), default=DEFAULT_ARTIFACTS_PATH)
@click.option("--slot-dir", type=click.Path(), default=DEFAULT_SLOT_DIR)
@click.option("--slot-pool-size", type=int, default=DEFAULT_SLOT_POOL_SIZE)
@click.option("--inference-url", default=DEFAULT_INFERENCE_URL)
@click.option("--model", default=DEFAULT_MODEL)
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(
    ctx: click.Context,
    db_path: str,
    artifacts_path: str,
    slot_dir: str,
    slot_pool_size: int,
    inference_url: str,
    model: str,
    verbose: bool,
) -> None:
    """Hestia - Local-first LLM agent framework."""
    # Ensure context object exists
    ctx.ensure_object(dict)

    # Initialize components
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    artifact_store = ArtifactStore(Path(artifacts_path))
    inference = InferenceClient(inference_url, model)
    session_store = SessionStore(db)
    policy = DefaultPolicyEngine()

    # Context builder with calibration
    calibration_path = Path("docs/calibration.json")
    context_builder = ContextBuilder.from_calibration_file(
        inference, policy, calibration_path
    )

    # Tool registry with built-in tools
    tool_registry = ToolRegistry(artifact_store)
    tool_registry.register(read_file)
    tool_registry.register(terminal)
    tool_registry.register(current_time)

    # Slot manager for KV-cache persistence
    slot_manager = SlotManager(
        inference=inference,
        session_store=session_store,
        slot_dir=Path(slot_dir),
        pool_size=slot_pool_size,
    )

    # Store in context
    ctx.obj["db"] = db
    ctx.obj["inference"] = inference
    ctx.obj["session_store"] = session_store
    ctx.obj["context_builder"] = context_builder
    ctx.obj["tool_registry"] = tool_registry
    ctx.obj["policy"] = policy
    ctx.obj["slot_manager"] = slot_manager
    ctx.obj["verbose"] = verbose


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize database, artifacts, and slot directories."""
    db: Database = ctx.obj["db"]
    artifacts_path = ctx.parent.params["artifacts_path"] if ctx.parent else DEFAULT_ARTIFACTS_PATH
    slot_dir = ctx.parent.params["slot_dir"] if ctx.parent else DEFAULT_SLOT_DIR

    async def _init() -> None:
        await db.init()
        Path(artifacts_path).mkdir(parents=True, exist_ok=True)
        Path(slot_dir).mkdir(parents=True, exist_ok=True)
        click.echo(f"Initialized database at {db}")
        click.echo(f"Initialized artifacts directory at {artifacts_path}")
        click.echo(f"Initialized slot directory at {slot_dir}")

    asyncio.run(_init())


@cli.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start an interactive chat session."""
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    verbose: bool = ctx.obj["verbose"]

    async def _chat() -> None:
        await db.init()

        # Get or create session for CLI user
        session = await session_store.get_or_create_session("cli", "default")
        click.echo(f"Session: {session.id}")
        click.echo("Type 'exit' or 'quit' to end the session, or /help for commands.\n")

        # Create orchestrator
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=10,
            slot_manager=slot_manager,
        )

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
    db: Database = ctx.obj["db"]
    inference: InferenceClient = ctx.obj["inference"]
    session_store: SessionStore = ctx.obj["session_store"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    verbose: bool = ctx.obj["verbose"]

    async def _ask() -> None:
        await db.init()

        session = await session_store.get_or_create_session("cli", "default")

        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=10,
            slot_manager=slot_manager,
        )

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
        await db.connect()
        await db.create_tables()

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

    async def _list() -> None:
        await db.connect()
        await db.create_tables()

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

    async def _show() -> None:
        await db.connect()
        await db.create_tables()

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
    db: Database = ctx.obj["db"]
    session_store: SessionStore = ctx.obj["session_store"]
    inference: InferenceClient = ctx.obj["inference"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]
    verbose: bool = ctx.obj["verbose"]

    async def _run() -> None:
        await db.connect()
        await db.create_tables()

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
            max_iterations=10,
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

    async def _enable() -> None:
        await db.connect()
        await db.create_tables()

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

    async def _disable() -> None:
        await db.connect()
        await db.create_tables()

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

    async def _remove() -> None:
        await db.connect()
        await db.create_tables()

        scheduler_store = SchedulerStore(db)
        success = await scheduler_store.delete_task(task_id)
        if not success:
            click.echo(f"Task not found: {task_id}", err=True)
            sys.exit(1)
        click.echo(f"Task {task_id} removed")

    asyncio.run(_remove())


@schedule.command(name="daemon")
@click.option("--tick-interval", type=float, default=5.0, help="Tick interval in seconds")
@click.pass_context
def schedule_daemon(ctx: click.Context, tick_interval: float) -> None:
    """Run the scheduler daemon (blocks until Ctrl-C)."""
    db: Database = ctx.obj["db"]
    session_store: SessionStore = ctx.obj["session_store"]
    inference: InferenceClient = ctx.obj["inference"]
    context_builder: ContextBuilder = ctx.obj["context_builder"]
    tool_registry: ToolRegistry = ctx.obj["tool_registry"]
    policy = ctx.obj["policy"]
    slot_manager: SlotManager = ctx.obj["slot_manager"]

    async def response_callback(task: ScheduledTask, text: str) -> None:
        click.echo(f"[scheduler:{task.id}] {text}")

    async def _daemon() -> None:
        await db.connect()
        await db.create_tables()

        scheduler_store = SchedulerStore(db)

        # Create orchestrator
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=10,
            slot_manager=slot_manager,
        )

        scheduler = Scheduler(
            scheduler_store=scheduler_store,
            session_store=session_store,
            orchestrator=orchestrator,
            response_callback=response_callback,
            tick_interval_seconds=tick_interval,
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


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
