"""Room management commands."""

from __future__ import annotations

import click
import httpx

from hestia.app import AppContext


async def _discover_telegram_chats(bot_token: str) -> list[dict[str, str]]:
    """Call Telegram Bot API getUpdates to find group chats the bot is in."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    chats: dict[str, dict[str, str]] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params={"limit": 100})
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            error = data.get("description", "Unknown Telegram API error")
            raise RuntimeError(error)
        for update in data.get("result", []):
            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat")
            if not chat:
                continue
            chat_type = chat.get("type", "")
            if chat_type not in ("group", "supergroup"):
                continue
            chat_id = str(chat["id"])
            if chat_id not in chats:
                chats[chat_id] = {
                    "id": chat_id,
                    "title": chat.get("title", chat_id),
                }
    return list(chats.values())


async def cmd_migrate_rooms(
    app: AppContext,
    telegram_groups: list[str] | None = None,
    auto_discover: bool = False,
) -> None:
    """Migrate existing group chats to the rooms table.

    Args:
        app: The application context.
        telegram_groups: Optional list of Telegram group chat IDs to register.
        auto_discover: If True, query Telegram Bot API for group chats.
    """
    from hestia.persistence.users import UserStore

    store = UserStore(app.db)

    # Find admin user
    admin_user = None
    for user in await store.list_users():
        if user.role == "admin":
            admin_user = user
            break

    created_rooms = 0
    skipped = 0

    groups_to_process: list[dict[str, str]] = []

    if auto_discover:
        telegram_cfg = app.config.platforms.telegram if app.config.platforms else None
        if telegram_cfg is None or not telegram_cfg.bot_token:
            click.echo("Telegram not configured — cannot auto-discover.")
            return
        click.echo("Querying Telegram for group chats…")
        groups_to_process = await _discover_telegram_chats(telegram_cfg.bot_token)
        click.echo(f"Found {len(groups_to_process)} group chat(s).")
    elif telegram_groups:
        groups_to_process = [
            {"id": str(g), "title": str(g)} for g in telegram_groups
        ]
    else:
        click.echo("Nothing to do. Use --telegram-group or --auto-discover.")
        return

    for group in groups_to_process:
        platform_room_id = group["id"]
        existing = await store.get_room_by_platform("telegram", platform_room_id)
        if existing:
            click.echo(f"  Skipping {platform_room_id}: already registered.")
            skipped += 1
            continue
        room = await store.create_room(
            "telegram", platform_room_id, display_name=group.get("title")
        )
        created_rooms += 1
        if admin_user is not None:
            await store.add_room_member(room.id, admin_user.id)
        click.echo(f"  Created room for Telegram group {platform_room_id}.")

    click.echo(f"Migrated {created_rooms} room(s), skipped {skipped}.")
