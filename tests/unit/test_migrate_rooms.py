"""Tests for the migrate-rooms CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hestia.commands.rooms import cmd_migrate_rooms
from hestia.config import HestiaConfig
from hestia.persistence.db import Database
from hestia.persistence.users import UserStore


@pytest.fixture
async def migrate_rooms_setup(tmp_path):
    """Create an AppContext-like mock with a fresh database."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.connect()
    await db.create_tables()

    cfg = HestiaConfig.default()
    app = MagicMock()
    app.db = db
    app.config = cfg

    yield app, db
    await db.close()


class TestMigrateRooms:
    @pytest.mark.asyncio
    async def test_migrate_telegram_groups(self, migrate_rooms_setup):
        app, db = migrate_rooms_setup
        store = UserStore(db)
        admin = await store.create_user("Admin", role="admin")

        await cmd_migrate_rooms(app, telegram_groups=["-1001234567890", "-1009876543210"])

        rooms = await store.list_rooms()
        assert len(rooms) == 2

        room1 = await store.get_room_by_platform("telegram", "-1001234567890")
        assert room1 is not None

        room2 = await store.get_room_by_platform("telegram", "-1009876543210")
        assert room2 is not None

        members1 = await store.get_room_members(room1.id)
        assert len(members1) == 1
        assert members1[0].id == admin.id

    @pytest.mark.asyncio
    async def test_migrate_rooms_idempotent(self, migrate_rooms_setup):
        app, db = migrate_rooms_setup
        store = UserStore(db)
        await store.create_user("Admin", role="admin")

        await cmd_migrate_rooms(app, telegram_groups=["-1001234567890"])
        rooms = await store.list_rooms()
        assert len(rooms) == 1

        # Second run should skip existing
        await cmd_migrate_rooms(app, telegram_groups=["-1001234567890"])
        rooms = await store.list_rooms()
        assert len(rooms) == 1

    @pytest.mark.asyncio
    async def test_migrate_rooms_no_groups(self, migrate_rooms_setup):
        app, db = migrate_rooms_setup
        await cmd_migrate_rooms(app, telegram_groups=None)

        store = UserStore(db)
        rooms = await store.list_rooms()
        assert len(rooms) == 0

    @pytest.mark.asyncio
    async def test_migrate_rooms_links_admin(self, migrate_rooms_setup):
        app, db = migrate_rooms_setup
        store = UserStore(db)
        admin = await store.create_user("Admin", role="admin")
        await store.create_user("User", role="user")

        await cmd_migrate_rooms(app, telegram_groups=["-1001234567890"])

        room = await store.get_room_by_platform("telegram", "-1001234567890")
        assert room is not None
        members = await store.get_room_members(room.id)
        assert len(members) == 1
        assert members[0].id == admin.id
