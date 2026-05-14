"""User management commands."""

from __future__ import annotations

import click

from hestia.app import AppContext


async def cmd_migrate_users(app: AppContext) -> None:
    """Migrate existing config users to the database."""
    from hestia.persistence.users import UserStore

    store = UserStore(app.db)

    # Read Telegram allowed_users
    telegram_users: list[str] = []
    if hasattr(app.config, "telegram") and app.config.telegram.bot_token:
        telegram_users = getattr(app.config.telegram, "allowed_users", [])

    # Read Matrix allowed_rooms
    matrix_rooms: list[str] = []
    if hasattr(app.config, "matrix") and app.config.matrix.access_token:
        matrix_rooms = getattr(app.config.matrix, "allowed_rooms", [])

    # Create users
    created = 0
    for i, user_id in enumerate(telegram_users):
        existing = await store.get_user_by_identity("telegram", str(user_id))
        if existing:
            continue

        role = "admin" if i == 0 else "user"
        user = await store.create_user(
            display_name=str(user_id),
            role=role,
        )
        await store.add_identity(user.id, "telegram", str(user_id))
        created += 1

    # For Matrix rooms, create a user for the first room (admin) and room entries
    for i, room_id in enumerate(matrix_rooms):
        existing = await store.get_user_by_identity("matrix", str(room_id))
        if existing:
            continue

        role = "admin" if i == 0 else "user"
        user = await store.create_user(
            display_name=str(room_id),
            role=role,
        )
        await store.add_identity(user.id, "matrix", str(room_id))
        created += 1

    click.echo(f"Migrated {created} user(s).")
