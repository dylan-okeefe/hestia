"""Tests for the migrate-users CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hestia.commands.users import cmd_migrate_users
from hestia.config import HestiaConfig
from hestia.persistence.db import Database
from hestia.persistence.users import UserStore


@pytest.fixture
async def migrate_setup(tmp_path):
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


class TestMigrateUsers:
    @pytest.mark.asyncio
    async def test_migrate_telegram_users(self, migrate_setup):
        app, db = migrate_setup
        app.config.telegram.bot_token = "token"
        app.config.telegram.allowed_users = ["111", "222", "333"]

        await cmd_migrate_users(app)

        store = UserStore(db)
        users = await store.list_users()
        assert len(users) == 3

        # First user is admin
        admin = await store.get_user_by_identity("telegram", "111")
        assert admin is not None
        assert admin.role == "admin"

        # Others are regular users
        user2 = await store.get_user_by_identity("telegram", "222")
        assert user2 is not None
        assert user2.role == "user"

    @pytest.mark.asyncio
    async def test_migrate_matrix_rooms(self, migrate_setup):
        app, db = migrate_setup
        app.config.matrix.access_token = "token"
        app.config.matrix.allowed_rooms = ["!room1:matrix.org", "!room2:matrix.org"]

        await cmd_migrate_users(app)

        store = UserStore(db)
        users = await store.list_users()
        assert len(users) == 2

        admin = await store.get_user_by_identity("matrix", "!room1:matrix.org")
        assert admin is not None
        assert admin.role == "admin"

        user2 = await store.get_user_by_identity("matrix", "!room2:matrix.org")
        assert user2 is not None
        assert user2.role == "user"

    @pytest.mark.asyncio
    async def test_migrate_skips_existing(self, migrate_setup):
        app, db = migrate_setup
        app.config.telegram.bot_token = "token"
        app.config.telegram.allowed_users = ["111"]

        # Pre-seed the user
        store = UserStore(db)
        user = await store.create_user("Existing", role="trusted")
        await store.add_identity(user.id, "telegram", "111")

        await cmd_migrate_users(app)

        users = await store.list_users()
        assert len(users) == 1
        existing = await store.get_user_by_identity("telegram", "111")
        assert existing.role == "trusted"

    @pytest.mark.asyncio
    async def test_migrate_no_platforms(self, migrate_setup):
        app, db = migrate_setup
        await cmd_migrate_users(app)

        store = UserStore(db)
        users = await store.list_users()
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_migrate_mixed_platforms(self, migrate_setup):
        app, db = migrate_setup
        app.config.telegram.bot_token = "token"
        app.config.telegram.allowed_users = ["111"]
        app.config.matrix.access_token = "token"
        app.config.matrix.allowed_rooms = ["!room1:matrix.org"]

        await cmd_migrate_users(app)

        store = UserStore(db)
        users = await store.list_users()
        assert len(users) == 2

        tg_user = await store.get_user_by_identity("telegram", "111")
        assert tg_user is not None
        assert tg_user.role == "admin"

        mx_user = await store.get_user_by_identity("matrix", "!room1:matrix.org")
        assert mx_user is not None
        assert mx_user.role == "admin"
