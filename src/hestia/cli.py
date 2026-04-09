"""CLI adapter for Hestia - local-first LLM agent framework."""

import asyncio
import sys
from pathlib import Path

import click

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.inference import InferenceClient
from hestia.core.types import Message
from hestia.orchestrator import Orchestrator
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.tools.builtin import current_time, read_file, terminal
from hestia.tools.registry import ToolRegistry


# Default configuration
DEFAULT_DB_PATH = Path("hestia.db")
DEFAULT_ARTIFACTS_PATH = Path("artifacts")
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


@click.group()
@click.option("--db-path", type=click.Path(), default=DEFAULT_DB_PATH)
@click.option("--artifacts-path", type=click.Path(), default=DEFAULT_ARTIFACTS_PATH)
@click.option("--inference-url", default=DEFAULT_INFERENCE_URL)
@click.option("--model", default=DEFAULT_MODEL)
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(
    ctx: click.Context,
    db_path: str,
    artifacts_path: str,
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

    # Store in context
    ctx.obj["db"] = db
    ctx.obj["inference"] = inference
    ctx.obj["session_store"] = session_store
    ctx.obj["context_builder"] = context_builder
    ctx.obj["tool_registry"] = tool_registry
    ctx.obj["policy"] = policy
    ctx.obj["verbose"] = verbose


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize database and artifacts directory."""
    db: Database = ctx.obj["db"]
    artifacts_path = ctx.parent.params["artifacts_path"] if ctx.parent else DEFAULT_ARTIFACTS_PATH

    async def _init() -> None:
        await db.init()
        Path(artifacts_path).mkdir(parents=True, exist_ok=True)
        click.echo(f"Initialized database at {db}")
        click.echo(f"Initialized artifacts directory at {artifacts_path}")

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
    verbose: bool = ctx.obj["verbose"]

    async def _chat() -> None:
        await db.init()

        # Get or create session for CLI user
        session = await session_store.get_or_create_session("cli", "default")
        click.echo(f"Session: {session.id}")
        click.echo("Type 'exit' or 'quit' to end the session.\n")

        # Create orchestrator
        orchestrator = Orchestrator(
            inference=inference,
            session_store=session_store,
            context_builder=context_builder,
            tool_registry=tool_registry,
            policy=policy,
            confirm_callback=CliConfirmHandler(),
            max_iterations=10,
        )

        response_handler = CliResponseHandler(verbose=verbose)

        while True:
            try:
                user_input = click.prompt("You", type=str)
                if user_input.lower() in ("exit", "quit"):
                    break

                user_message = Message(role="user", content=user_input)

                await orchestrator.process_turn(
                    session=session,
                    user_message=user_message,
                    respond_callback=response_handler,
                )

            except KeyboardInterrupt:
                click.echo("\nUse 'exit' or 'quit' to end the session.")
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


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
