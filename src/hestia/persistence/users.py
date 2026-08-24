"""User, identity, and room persistence."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from hestia.core.clock import utcnow
from hestia.persistence.schema import room_members, rooms, user_identities

logger = logging.getLogger(__name__)


def is_matrix_room_id(value: str) -> bool:
    """Return True if ``value`` is a Matrix room ID or alias.

    Matrix room IDs start with ``!`` and aliases start with ``#``.
    Neither is a valid user identity.
    """
    return bool(value) and value.startswith(("!", "#"))

if TYPE_CHECKING:
    from hestia.persistence.db import Database


@dataclass
class User:
    id: str
    display_name: str
    role: str
    trust_preset: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UserIdentity:
    user_id: str
    platform: str
    platform_user: str
    verified: bool
    created_at: datetime


@dataclass
class Room:
    id: str
    platform: str
    platform_room_id: str
    display_name: str | None
    created_at: datetime


@dataclass
class RoomMember:
    room_id: str
    user_id: str
    joined_at: datetime


class UserStore:
    """Store for users, identities, rooms, and room memberships."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- User methods ---

    async def create_user(
        self,
        display_name: str,
        role: str = "user",
        trust_preset: str | None = None,
        notes: str | None = None,
    ) -> User:
        now = utcnow()
        user_id = uuid.uuid4().hex
        sql = sa.text(
            "INSERT INTO users (id, display_name, role, trust_preset, notes, "
            "created_at, updated_at) "
            "VALUES (:id, :display_name, :role, :trust_preset, :notes, "
            ":created_at, :updated_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": user_id,
                    "display_name": display_name,
                    "role": role,
                    "trust_preset": trust_preset,
                    "notes": notes,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
            )
            await conn.commit()
        return User(
            id=user_id,
            display_name=display_name,
            role=role,
            trust_preset=trust_preset,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

    async def get_user(self, user_id: str) -> User | None:
        sql = sa.text(
            "SELECT id, display_name, role, trust_preset, notes, created_at, updated_at "
            "FROM users WHERE id = :id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": user_id})
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_user(row)

    async def get_user_by_identity(self, platform: str, platform_user: str) -> User | None:
        sql = sa.text(
            "SELECT u.id, u.display_name, u.role, u.trust_preset, u.notes, "
            "u.created_at, u.updated_at "
            "FROM users u JOIN user_identities ui ON u.id = ui.user_id "
            "WHERE ui.platform = :platform AND ui.platform_user = :platform_user"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"platform": platform, "platform_user": platform_user})
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_user(row)

    async def list_users(self) -> list[User]:
        sql = sa.text(
            "SELECT id, display_name, role, trust_preset, notes, created_at, updated_at FROM users"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql)
            rows = result.fetchall()
            return [self._row_to_user(row) for row in rows]

    async def update_user(self, user_id: str, **fields: Any) -> User | None:
        allowed = {"display_name", "role", "trust_preset", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get_user(user_id)

        updates["updated_at"] = utcnow().isoformat()
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        sql = sa.text(f"UPDATE users SET {set_clause} WHERE id = :id")

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": user_id, **updates})
            await conn.commit()
            if result.rowcount == 0:
                return None
        return await self.get_user(user_id)

    async def delete_user(self, user_id: str) -> bool:
        async with self._db.engine.connect() as conn:
            # Manual cascade for SQLite without PRAGMA foreign_keys
            await conn.execute(
                sa.text("DELETE FROM room_members WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            await conn.execute(
                sa.text("DELETE FROM user_identities WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            result = await conn.execute(
                sa.text("DELETE FROM users WHERE id = :id"), {"id": user_id}
            )
            await conn.commit()
            return result.rowcount > 0

    # --- Identity methods ---

    async def add_identity(
        self, user_id: str, platform: str, platform_user: str, verified: bool = False
    ) -> None:
        if is_matrix_room_id(platform_user):
            raise ValueError(
                f"Refusing to add Matrix room ID/alias {platform_user!r} as a user identity"
            )
        sql = sa.text(
            "INSERT INTO user_identities (user_id, platform, platform_user, verified, created_at) "
            "VALUES (:user_id, :platform, :platform_user, :verified, :created_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "user_id": user_id,
                    "platform": platform,
                    "platform_user": platform_user,
                    "verified": 1 if verified else 0,
                    "created_at": utcnow().isoformat(),
                },
            )
            await conn.commit()

    async def remove_identity(self, platform: str, platform_user: str) -> bool:
        sql = sa.text(
            "DELETE FROM user_identities "
            "WHERE platform = :platform AND platform_user = :platform_user"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"platform": platform, "platform_user": platform_user})
            await conn.commit()
            return result.rowcount > 0

    async def get_identities(self, user_id: str) -> list[UserIdentity]:
        sql = sa.text(
            "SELECT user_id, platform, platform_user, verified, created_at "
            "FROM user_identities WHERE user_id = :user_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"user_id": user_id})
            rows = result.fetchall()
            return [self._row_to_identity(row) for row in rows]

    async def get_identities_for_users(self, user_ids: list[str]) -> dict[str, list[UserIdentity]]:
        if not user_ids:
            return {}
        query = sa.select(user_identities).where(user_identities.c.user_id.in_(user_ids))
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
        grouped: dict[str, list[UserIdentity]] = {}
        for row in rows:
            identity = self._row_to_identity(row)
            grouped.setdefault(row.user_id, []).append(identity)
        return grouped

    async def get_rooms_for_users(self, user_ids: list[str]) -> dict[str, list[Room]]:
        if not user_ids:
            return {}
        query = (
            sa.select(
                rooms.c.id,
                rooms.c.platform,
                rooms.c.platform_room_id,
                rooms.c.display_name,
                rooms.c.created_at,
                room_members.c.user_id,
            )
            .select_from(rooms.join(room_members, rooms.c.id == room_members.c.room_id))
            .where(room_members.c.user_id.in_(user_ids))
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()
        grouped: dict[str, list[Room]] = {}
        for row in rows:
            room = self._row_to_room(row)
            grouped.setdefault(row.user_id, []).append(room)
        return grouped

    async def cleanup_matrix_room_id_identities(self) -> tuple[int, int]:
        """Remove identities that are Matrix room IDs/aliases and any now-empty users.

        Returns the number of removed identities and removed users. Idempotent:
        repeated calls remove nothing once the bad rows are gone.

        Emits structured INFO audit logs for every removed identity and user so the
        cleanup is traceable.
        """
        removed_identities = 0
        removed_users = 0

        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sa.text(
                    "SELECT user_id, platform_user FROM user_identities "
                    "WHERE platform = :platform AND (platform_user LIKE '!%' OR platform_user LIKE '#%')"
                ),
                {"platform": "matrix"},
            )
            bad_rows = result.fetchall()

            affected_user_ids = {row.user_id for row in bad_rows}
            # platform_user is unique per platform, so this maps cleanly to one user_id.
            identity_user_map = {row.platform_user: row.user_id for row in bad_rows}

            for platform_user in identity_user_map:
                user_id = identity_user_map[platform_user]
                result = await conn.execute(
                    sa.text(
                        "DELETE FROM user_identities "
                        "WHERE platform = :platform AND platform_user = :platform_user"
                    ),
                    {"platform": "matrix", "platform_user": platform_user},
                )
                removed_identities += result.rowcount
                logger.info(
                    "cleanup_matrix_room_id_identities removed identity",
                    extra={"user_id": user_id, "platform_user": platform_user},
                )

            for user_id in affected_user_ids:
                remaining = await conn.execute(
                    sa.text(
                        "SELECT COUNT(*) AS count FROM user_identities WHERE user_id = :user_id"
                    ),
                    {"user_id": user_id},
                )
                row = remaining.fetchone()
                if row is not None and row[0] == 0:
                    await conn.execute(
                        sa.text("DELETE FROM room_members WHERE user_id = :user_id"),
                        {"user_id": user_id},
                    )
                    result = await conn.execute(
                        sa.text("DELETE FROM users WHERE id = :id"),
                        {"id": user_id},
                    )
                    removed_users += result.rowcount
                    logger.info(
                        "cleanup_matrix_room_id_identities removed user",
                        extra={"user_id": user_id},
                    )

            await conn.commit()

        return removed_identities, removed_users

    # --- Room methods ---

    async def create_room(
        self, platform: str, platform_room_id: str, display_name: str | None = None
    ) -> Room:
        now = utcnow()
        room_id = uuid.uuid4().hex
        sql = sa.text(
            "INSERT INTO rooms (id, platform, platform_room_id, display_name, created_at) "
            "VALUES (:id, :platform, :platform_room_id, :display_name, :created_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "id": room_id,
                    "platform": platform,
                    "platform_room_id": platform_room_id,
                    "display_name": display_name,
                    "created_at": now.isoformat(),
                },
            )
            await conn.commit()
        return Room(
            id=room_id,
            platform=platform,
            platform_room_id=platform_room_id,
            display_name=display_name,
            created_at=now,
        )

    async def get_room(self, room_id: str) -> Room | None:
        sql = sa.text(
            "SELECT id, platform, platform_room_id, display_name, created_at "
            "FROM rooms WHERE id = :id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": room_id})
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_room(row)

    async def get_room_by_platform(self, platform: str, platform_room_id: str) -> Room | None:
        sql = sa.text(
            "SELECT id, platform, platform_room_id, display_name, created_at FROM rooms "
            "WHERE platform = :platform AND platform_room_id = :platform_room_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(
                sql, {"platform": platform, "platform_room_id": platform_room_id}
            )
            row = result.fetchone()
            if row is None:
                return None
            return self._row_to_room(row)

    async def list_rooms(self) -> list[Room]:
        sql = sa.text(
            "SELECT id, platform, platform_room_id, display_name, created_at FROM rooms"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql)
            rows = result.fetchall()
            return [self._row_to_room(row) for row in rows]

    async def update_room(self, room_id: str, **fields: Any) -> Room | None:
        allowed = {"platform", "platform_room_id", "display_name"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get_room(room_id)

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        sql = sa.text(f"UPDATE rooms SET {set_clause} WHERE id = :id")

        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"id": room_id, **updates})
            await conn.commit()
            if result.rowcount == 0:
                return None
        return await self.get_room(room_id)

    async def delete_room(self, room_id: str) -> bool:
        async with self._db.engine.connect() as conn:
            # Manual cascade for SQLite without PRAGMA foreign_keys
            await conn.execute(
                sa.text("DELETE FROM room_members WHERE room_id = :room_id"),
                {"room_id": room_id},
            )
            result = await conn.execute(
                sa.text("DELETE FROM rooms WHERE id = :id"), {"id": room_id}
            )
            await conn.commit()
            return result.rowcount > 0

    # --- Room member methods ---

    async def add_room_member(self, room_id: str, user_id: str) -> None:
        sql = sa.text(
            "INSERT INTO room_members (room_id, user_id, joined_at) "
            "VALUES (:room_id, :user_id, :joined_at)"
        )
        async with self._db.engine.connect() as conn:
            await conn.execute(
                sql,
                {
                    "room_id": room_id,
                    "user_id": user_id,
                    "joined_at": utcnow().isoformat(),
                },
            )
            await conn.commit()

    async def remove_room_member(self, room_id: str, user_id: str) -> bool:
        sql = sa.text(
            "DELETE FROM room_members WHERE room_id = :room_id AND user_id = :user_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"room_id": room_id, "user_id": user_id})
            await conn.commit()
            return result.rowcount > 0

    async def get_room_members(self, room_id: str) -> list[User]:
        sql = sa.text(
            "SELECT u.id, u.display_name, u.role, u.trust_preset, u.notes, "
            "u.created_at, u.updated_at "
            "FROM users u JOIN room_members rm ON u.id = rm.user_id "
            "WHERE rm.room_id = :room_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"room_id": room_id})
            rows = result.fetchall()
            return [self._row_to_user(row) for row in rows]

    async def get_user_rooms(self, user_id: str) -> list[Room]:
        sql = sa.text(
            "SELECT r.id, r.platform, r.platform_room_id, r.display_name, r.created_at "
            "FROM rooms r JOIN room_members rm ON r.id = rm.room_id "
            "WHERE rm.user_id = :user_id"
        )
        async with self._db.engine.connect() as conn:
            result = await conn.execute(sql, {"user_id": user_id})
            rows = result.fetchall()
            return [self._row_to_room(row) for row in rows]

    # --- Row converters ---

    def _row_to_user(self, row: Any) -> User:
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        updated_at = row.updated_at
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return User(
            id=row.id,
            display_name=row.display_name,
            role=row.role,
            trust_preset=row.trust_preset,
            notes=row.notes,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_identity(self, row: Any) -> UserIdentity:
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return UserIdentity(
            user_id=row.user_id,
            platform=row.platform,
            platform_user=row.platform_user,
            verified=bool(row.verified),
            created_at=created_at,
        )

    def _row_to_room(self, row: Any) -> Room:
        created_at = row.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return Room(
            id=row.id,
            platform=row.platform,
            platform_room_id=row.platform_room_id,
            display_name=row.display_name,
            created_at=created_at,
        )
