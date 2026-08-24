"""Deprecated re-export facade for the persistence stores.

Import ``SessionStore`` from ``hestia.persistence.session_store``,
``MessageStore`` from ``hestia.persistence.message_store``, and
``TurnStore`` from ``hestia.persistence.turn_store`` instead.

This module will be removed in v0.16.0.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "hestia.persistence.sessions is deprecated; import SessionStore from "
    "hestia.persistence.session_store, MessageStore from hestia.persistence.message_store, "
    "and TurnStore from hestia.persistence.turn_store. This module will be removed in v0.16.0.",
    DeprecationWarning,
    stacklevel=2,
)

from hestia.persistence.message_store import MessageStore  # noqa: E402
from hestia.persistence.session_store import SessionStore  # noqa: E402
from hestia.persistence.turn_store import TurnStore  # noqa: E402

__all__ = ["SessionStore", "MessageStore", "TurnStore"]
