"""User management commands."""

from __future__ import annotations

import click

from hestia.app import AppContext


async def cmd_migrate_users(app: AppContext) -> None:
    """Migrate existing config users to the database."""
    from hestia.persistence.users import User, UserStore

    store = UserStore(app.db)

    # Find existing admin if any
    admin_user: User | None = None
    for user in await store.list_users():
        if user.role == "admin":
            admin_user = user
            break

    # Read Telegram allowed_users
    telegram_users: list[str] = []
    if hasattr(app.config, "telegram") and app.config.telegram.bot_token:
        telegram_users = getattr(app.config.telegram, "allowed_users", [])

    # Read Matrix allowed_rooms
    matrix_entries: list[str] = []
    if hasattr(app.config, "matrix") and app.config.matrix.access_token:
        matrix_entries = getattr(app.config.matrix, "allowed_rooms", [])

    created_users = 0
    created_rooms = 0

    # Process Telegram users (always users)
    for user_id in telegram_users:
        platform_user = str(user_id)
        existing_user = await store.get_user_by_identity("telegram", platform_user)
        if existing_user:
            if admin_user is None:
                admin_user = existing_user
            continue

        role = "admin" if admin_user is None else "user"
        user = await store.create_user(
            display_name=platform_user,
            role=role,
        )
        await store.add_identity(user.id, "telegram", platform_user)
        created_users += 1
        if admin_user is None:
            admin_user = user

    # Process Matrix entries
    for entry in matrix_entries:
        platform_user = str(entry)
        if platform_user.startswith("!"):
            # Room ID - create Room record
            existing_room = await store.get_room_by_platform("matrix", platform_user)
            if existing_room:
                continue
            room = await store.create_room("matrix", platform_user, display_name=None)
            created_rooms += 1
            if admin_user is not None:
                await store.add_room_member(room.id, admin_user.id)
        else:
            # User ID (starts with @ or other format)
            existing_user = await store.get_user_by_identity("matrix", platform_user)
            if existing_user:
                if admin_user is None:
                    admin_user = existing_user
                continue

            role = "admin" if admin_user is None else "user"
            user = await store.create_user(
                display_name=platform_user,
                role=role,
            )
            await store.add_identity(user.id, "matrix", platform_user)
            created_users += 1
            if admin_user is None:
                admin_user = user

    # Telegram group chats: the adapter does not expose an enumeration API.
    # Rooms will be auto-registered on the next group message.
    telegram_groups_found = False
    if (
        hasattr(app.config, "telegram")
        and app.config.telegram.bot_token
        and telegram_users
    ):
        # The running adapter may have group chat state, but it is not available
        # in the CLI context. Log a note so the admin knows what to expect.
        pass

    if not telegram_groups_found:
        click.echo(
            "No Telegram group chats found for migration. "
            "Rooms will be auto-registered on next group message."
        )

    click.echo(f"Migrated {created_users} user(s) and {created_rooms} room(s).")
