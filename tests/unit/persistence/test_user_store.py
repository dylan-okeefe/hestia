"""Tests for UserStore persistence."""

from __future__ import annotations

import pytest

from hestia.persistence.db import Database
from hestia.persistence.users import UserStore


@pytest.fixture
async def user_store(tmp_path):
    """Create a UserStore with a fresh database."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.connect()
    await db.create_tables()
    store = UserStore(db)
    yield store
    await db.close()


class TestUserStore:
    @pytest.mark.asyncio
    async def test_create_and_get_user(self, user_store):
        user = await user_store.create_user("Dylan", role="admin", trust_preset="developer")
        assert user.display_name == "Dylan"
        assert user.role == "admin"
        assert user.trust_preset == "developer"

        fetched = await user_store.get_user(user.id)
        assert fetched is not None
        assert fetched.display_name == "Dylan"
        assert fetched.role == "admin"

    @pytest.mark.asyncio
    async def test_list_users(self, user_store):
        await user_store.create_user("Alice")
        await user_store.create_user("Bob")
        users = await user_store.list_users()
        assert len(users) == 2
        names = {u.display_name for u in users}
        assert names == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_update_user(self, user_store):
        user = await user_store.create_user("Alice", role="user")
        updated = await user_store.update_user(user.id, display_name="Alicia", role="trusted")
        assert updated is not None
        assert updated.display_name == "Alicia"
        assert updated.role == "trusted"

    @pytest.mark.asyncio
    async def test_update_user_no_fields(self, user_store):
        user = await user_store.create_user("Alice")
        updated = await user_store.update_user(user.id)
        assert updated is not None
        assert updated.display_name == "Alice"

    @pytest.mark.asyncio
    async def test_update_user_clears_fields(self, user_store):
        user = await user_store.create_user(
            "Alice", trust_preset="developer", notes="some notes"
        )
        updated = await user_store.update_user(
            user.id, trust_preset=None, notes=""
        )
        assert updated is not None
        assert updated.trust_preset is None
        assert updated.notes == ""

    @pytest.mark.asyncio
    async def test_update_room_clears_display_name(self, user_store):
        room = await user_store.create_room(
            "telegram", "-100123", display_name="Old"
        )
        updated = await user_store.update_room(room.id, display_name=None)
        assert updated is not None
        assert updated.display_name is None

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, user_store):
        updated = await user_store.update_user("nonexistent", display_name="X")
        assert updated is None

    @pytest.mark.asyncio
    async def test_delete_user_cascades_to_identities(self, user_store):
        user = await user_store.create_user("Alice")
        await user_store.add_identity(user.id, "telegram", "12345")
        deleted = await user_store.delete_user(user.id)
        assert deleted is True

        fetched = await user_store.get_user(user.id)
        assert fetched is None

        identities = await user_store.get_identities(user.id)
        assert identities == []

    @pytest.mark.asyncio
    async def test_delete_user_cascades_to_room_members(self, user_store):
        user = await user_store.create_user("Alice")
        await user_store.add_identity(user.id, "telegram", "12345")
        room = await user_store.create_room("telegram", "-100123")
        await user_store.add_room_member(room.id, user.id)

        deleted = await user_store.delete_user(user.id)
        assert deleted is True

        fetched = await user_store.get_user(user.id)
        assert fetched is None

        members = await user_store.get_room_members(room.id)
        assert members == []

    @pytest.mark.asyncio
    async def test_add_and_get_identities(self, user_store):
        user = await user_store.create_user("Alice")
        await user_store.add_identity(user.id, "telegram", "12345", verified=True)
        await user_store.add_identity(user.id, "matrix", "@alice:matrix.org")

        identities = await user_store.get_identities(user.id)
        assert len(identities) == 2
        platforms = {i.platform for i in identities}
        assert platforms == {"telegram", "matrix"}

        telegram = next(i for i in identities if i.platform == "telegram")
        assert telegram.verified is True

    @pytest.mark.asyncio
    async def test_get_user_by_identity(self, user_store):
        user = await user_store.create_user("Alice")
        await user_store.add_identity(user.id, "telegram", "12345")

        fetched = await user_store.get_user_by_identity("telegram", "12345")
        assert fetched is not None
        assert fetched.id == user.id

        missing = await user_store.get_user_by_identity("telegram", "99999")
        assert missing is None

    @pytest.mark.asyncio
    async def test_remove_identity(self, user_store):
        user = await user_store.create_user("Alice")
        await user_store.add_identity(user.id, "telegram", "12345")

        removed = await user_store.remove_identity("telegram", "12345")
        assert removed is True

        identities = await user_store.get_identities(user.id)
        assert identities == []

        removed_again = await user_store.remove_identity("telegram", "12345")
        assert removed_again is False

    @pytest.mark.asyncio
    async def test_duplicate_identity_fails(self, user_store):
        user = await user_store.create_user("Alice")
        await user_store.add_identity(user.id, "telegram", "12345")

        with pytest.raises(Exception):
            await user_store.add_identity(user.id, "telegram", "12345")

    @pytest.mark.asyncio
    async def test_create_and_get_room(self, user_store):
        room = await user_store.create_room("telegram", "-100123", display_name="Family chat")
        assert room.platform == "telegram"
        assert room.platform_room_id == "-100123"
        assert room.display_name == "Family chat"

        fetched = await user_store.get_room(room.id)
        assert fetched is not None
        assert fetched.display_name == "Family chat"

    @pytest.mark.asyncio
    async def test_get_room_by_platform(self, user_store):
        await user_store.create_room("matrix", "!room:matrix.org", display_name="Dev")
        fetched = await user_store.get_room_by_platform("matrix", "!room:matrix.org")
        assert fetched is not None
        assert fetched.display_name == "Dev"

        missing = await user_store.get_room_by_platform("matrix", "!other:matrix.org")
        assert missing is None

    @pytest.mark.asyncio
    async def test_list_rooms(self, user_store):
        await user_store.create_room("telegram", "-100123")
        await user_store.create_room("matrix", "!room:matrix.org")
        rooms = await user_store.list_rooms()
        assert len(rooms) == 2

    @pytest.mark.asyncio
    async def test_update_room(self, user_store):
        room = await user_store.create_room("telegram", "-100123", display_name="Old")
        updated = await user_store.update_room(room.id, display_name="New")
        assert updated is not None
        assert updated.display_name == "New"

    @pytest.mark.asyncio
    async def test_delete_room_cascades_to_members(self, user_store):
        user = await user_store.create_user("Alice")
        room = await user_store.create_room("telegram", "-100123")
        await user_store.add_room_member(room.id, user.id)

        deleted = await user_store.delete_room(room.id)
        assert deleted is True

        fetched = await user_store.get_room(room.id)
        assert fetched is None

        members = await user_store.get_room_members(room.id)
        assert members == []

    @pytest.mark.asyncio
    async def test_add_room_member_and_get_room_members(self, user_store):
        user = await user_store.create_user("Alice")
        room = await user_store.create_room("telegram", "-100123")
        await user_store.add_room_member(room.id, user.id)

        members = await user_store.get_room_members(room.id)
        assert len(members) == 1
        assert members[0].id == user.id

    @pytest.mark.asyncio
    async def test_remove_room_member(self, user_store):
        user = await user_store.create_user("Alice")
        room = await user_store.create_room("telegram", "-100123")
        await user_store.add_room_member(room.id, user.id)

        removed = await user_store.remove_room_member(room.id, user.id)
        assert removed is True

        members = await user_store.get_room_members(room.id)
        assert members == []

    @pytest.mark.asyncio
    async def test_get_user_rooms(self, user_store):
        user = await user_store.create_user("Alice")
        room1 = await user_store.create_room("telegram", "-100123")
        room2 = await user_store.create_room("matrix", "!room:matrix.org")
        await user_store.add_room_member(room1.id, user.id)
        await user_store.add_room_member(room2.id, user.id)

        rooms = await user_store.get_user_rooms(user.id)
        assert len(rooms) == 2
        room_ids = {r.id for r in rooms}
        assert room_ids == {room1.id, room2.id}

    @pytest.mark.asyncio
    async def test_duplicate_room_fails(self, user_store):
        await user_store.create_room("telegram", "-100123")
        with pytest.raises(Exception):
            await user_store.create_room("telegram", "-100123")
