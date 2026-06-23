"""Tests for the deprecated hestia.persistence.sessions re-export facade."""

import warnings

import pytest

from hestia.persistence.db import Database


def test_facade_emits_deprecation_warning():
    """Importing from the facade module warns about deprecation."""
    import importlib

    import hestia.persistence.sessions

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(hestia.persistence.sessions)
        from hestia.persistence.sessions import (
            MessageStore,
            SessionStore,
            TurnStore,
        )

    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    warning_text = " ".join(str(w.message) for w in caught)
    assert "deprecated" in warning_text.lower()
    assert "hestia.persistence.session_store" in warning_text


def test_facade_exports_same_classes():
    """The facade re-exports the same classes as the new modules."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from hestia.persistence.message_store import MessageStore as NewMessageStore
        from hestia.persistence.sessions import (
            MessageStore as FacadeMessageStore,
            SessionStore as FacadeSessionStore,
            TurnStore as FacadeTurnStore,
        )
        from hestia.persistence.session_store import SessionStore as NewSessionStore
        from hestia.persistence.turn_store import TurnStore as NewTurnStore

    assert FacadeSessionStore is NewSessionStore
    assert FacadeMessageStore is NewMessageStore
    assert FacadeTurnStore is NewTurnStore


@pytest.mark.asyncio
async def test_facade_session_store_still_works(tmp_path):
    """Session-only operations on the re-exported SessionStore still function."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from hestia.persistence.sessions import SessionStore

    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    try:
        store = SessionStore(db)
        session = await store.get_or_create_session("test", "user1")
        assert session.platform == "test"
        assert session.platform_user == "user1"
    finally:
        await db.close()
