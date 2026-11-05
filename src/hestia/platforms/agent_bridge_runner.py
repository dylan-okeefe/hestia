"""Polling-loop runner for ``hestia coder-bot`` (L233).

Deliberately free of orchestrator, scheduler, and inference wiring: the
Telegram coding-agent bridge must keep working while ``hestia serve`` (and
Strata) are down. Only the Telegram adapter, the AgentBridge, and the Pi
children are involved.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
import signal

import click

from hestia.config import HestiaConfig
from hestia.persistence.chat_settings import ChatSettingsStore
from hestia.persistence.db import Database
from hestia.platforms.agent_bridge import AgentBridge
from hestia.platforms.telegram_adapter import TelegramAdapter

logger = logging.getLogger(__name__)

# Provided at runtime via a systemd EnvironmentFile (mode 600); never logged.
_BOT_TOKEN_ENV = "HESTIA_TG_BOT_TOKEN"


async def _build_coder_bot(
    config: HestiaConfig, token: str
) -> tuple[TelegramAdapter, AgentBridge, Database]:
    """Compose the coder-bot adapter + bridge backed by a per-chat settings store.

    The store persists /agent backend selections and kimi session ids across
    restarts; both the adapter (command handler) and the bridge (dispatch)
    share one instance, mirroring the serve-mode wiring in runners.py.
    """
    eff_cfg = dataclasses.replace(config.telegram, bot_token=token, agent_bridge_enabled=True)
    db = Database(config.storage.database_url)
    await db.connect()
    try:
        await db.create_tables()
    except Exception:
        await db.close()
        raise
    chat_settings_store = ChatSettingsStore(db)
    adapter = TelegramAdapter(eff_cfg)
    adapter.set_chat_settings_store(chat_settings_store)
    bridge = AgentBridge(adapter=adapter, config=eff_cfg, chat_settings_store=chat_settings_store)
    adapter.set_agent_bridge(bridge)
    return adapter, bridge, db


async def run_coder_bot(config: HestiaConfig) -> None:
    """Run the Telegram coding-agent bridge until SIGINT/SIGTERM.

    Raises ``click.UsageError`` on configuration problems (caller maps that to
    a clean exit message).
    """
    tg_cfg = config.telegram
    if not tg_cfg.agent_bridge_enabled:
        raise click.UsageError(
            "coder-bot requires the agent bridge: set telegram.agent_bridge_enabled=true "
            "or HESTIA_TELEGRAM_AGENT_BRIDGE_ENABLED=1"
        )
    token = os.environ.get(_BOT_TOKEN_ENV) or tg_cfg.bot_token
    if not token:
        raise click.UsageError(
            f"coder-bot requires a bot token: set {_BOT_TOKEN_ENV} or telegram.bot_token"
        )
    if not tg_cfg.agent_bridge_chats:
        click.echo(
            "Warning: telegram.agent_bridge_chats is empty — no chat will be routed "
            "to the coding agent.",
            err=True,
        )
        logger.warning("agent_bridge_chats is empty; all messages fall through")

    adapter, bridge, db = await _build_coder_bot(config, token)

    await adapter.start(None)
    click.echo("Coder bot started (agent bridge mode). Press Ctrl-C to stop.")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)
    try:
        await stop_event.wait()
    finally:
        await adapter.stop()
        await db.close()
