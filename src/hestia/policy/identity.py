"""Identity representation for policy decisions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    """A human actor resolved to a platform identity.

    The ``platform:platform_user`` pair is the primary key for trust lookups.
    ``user_id`` is populated when the identity is linked to a row in the
    ``users`` table.
    """

    platform: str
    platform_user: str
    user_id: str | None = None
