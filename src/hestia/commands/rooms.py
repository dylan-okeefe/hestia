"""Room management commands."""

from __future__ import annotations

import click

from hestia.app import AppContext


async def cmd_migrate_rooms(
    app: AppContext, telegram_groups: list[str] | None = None
) -> None:
    """Migrate existing group chats to the rooms table.

    Args:
        app: The application context.
        telegram_groups: Optional list of Telegram group chat IDs to register.
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

    if telegram_groups:
        for chat_id in telegram_groups:
            platform_room_id = str(chat_id)
            existing = await store.get_room_by_platform("telegram", platform_room_id)
            if existing:
                click.echo(
                    f"Skipping {platform_room_id}: already registered."
                )
                continue
            room = await store.create_room(
                "telegram", platform_room_id, display_name=None
            )
            created_rooms += 1
            if admin_user is not None:
                await store.add_room_member(room.id, admin_user.id)
            click.echo(f"Created room for Telegram group {platform_room_id}.")

    click.echo(f"Migrated {created_rooms} room(s).")
