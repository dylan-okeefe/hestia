"""Chat-related command implementations."""

from __future__ import annotations

import logging

import click
import httpx

from hestia.app import (
    CliAppContext,
    CliConfirmHandler,
    CliResponseHandler,
)
from hestia.commands._shared import _format_token_usage
from hestia.commands.meta import _handle_meta_command
from hestia.core.types import Message
from hestia.errors import HestiaError
from hestia.persistence.memory_epochs import _compile_and_set_memory_epoch

logger = logging.getLogger(__name__)


async def cmd_chat(app: CliAppContext, new_session: bool = False) -> None:
    """Start an interactive chat session."""
    if not app.config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    app.set_confirm_callback(CliConfirmHandler())
    orchestrator = app.make_orchestrator()

    # Recover stale turns from previous crash
    recovered = await orchestrator.recover_stale_turns()
    if recovered:
        click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

    if new_session:
        session = await app.session_store.create_session("cli", "default")
        click.echo(f"New session: {session.id}")
    else:
        session = await app.session_store.get_or_create_session("cli", "default")
        click.echo(f"Session: {session.id}")

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
            turn = await orchestrator.process_turn(
                session=session,
                user_message=user_message,
                respond_callback=response_handler,
            )
            if app.verbose:
                trace = await app.trace_store.get_by_turn(turn.id)
                usage = _format_token_usage(trace)
                if usage:
                    click.echo(usage)
        except KeyboardInterrupt:
            click.echo("\nUse /quit or /exit to end the session.")
        except (HestiaError, httpx.HTTPError, OSError) as e:
            click.echo(f"Error: {e}", err=True)
            if app.verbose:
                import traceback

                traceback.print_exc()

    click.echo("Goodbye!")


async def cmd_ask(app: CliAppContext, message: str) -> None:
    """Send a single message and get a response."""
    if not app.config.inference.model_name:
        raise ValueError(
            "inference.model_name is required — set it to your llama.cpp model filename "
            "(e.g. 'my-model-Q4_K_M.gguf')"
        )
    app.set_confirm_callback(CliConfirmHandler())
    orchestrator = app.make_orchestrator()

    recovered = await orchestrator.recover_stale_turns()
    if recovered:
        click.echo(f"Recovered {recovered} stale turn(s) from previous crash.")

    session = await app.session_store.get_or_create_session("cli", "default")
    await _compile_and_set_memory_epoch(app, session)

    user_message = Message(role="user", content=message)

    response_handler = CliResponseHandler(verbose=app.verbose)

    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=response_handler,
    )
    if app.verbose:
        trace = await app.trace_store.get_by_turn(turn.id)
        usage = _format_token_usage(trace)
        if usage:
            click.echo(usage)
