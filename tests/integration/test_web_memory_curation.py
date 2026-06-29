"""Integration tests for memory curation web routes (Loop C)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hestia.config import WebConfig
from hestia.memory.store import MemoryStore
from hestia.memory.topics import TopicStore
from hestia.persistence.db import Database
from hestia.web.api import create_web_app
from hestia.web.auth import AuthManager, AuthMiddleware
from hestia.web.context import WebContext, set_web_context


@pytest.fixture(autouse=True)
def _clear_web_context() -> None:
    from hestia.web import context as ctx_mod

    ctx_mod._ctx = None


@pytest.fixture
async def db():
    """In-memory database with schema and memory table."""
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.connect()
    await database.create_tables()
    memory_store = MemoryStore(database)
    await memory_store.create_table()
    yield database
    await database.close()


@pytest.fixture
async def mock_app(db) -> MagicMock:
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.telegram = MagicMock(bot_token="", allowed_users=[])
    mock.config.matrix = MagicMock(
        homeserver="", user_id="", access_token="", allowed_rooms=[]
    )
    mock.config.email = MagicMock(
        imap_host="", username="", password="", password_env=""
    )
    mock.config.storage = MagicMock(allowed_roots=["."])
    mock.config.inference = MagicMock(base_url="")
    mock.config.security = MagicMock(injection_scanner_enabled=False)
    mock.config.web_search = MagicMock()
    mock.config.trust = MagicMock(preset=None)
    mock.config.rate_limit = MagicMock()
    mock.config.features = MagicMock()
    mock.config.features.web = MagicMock(
        enabled=True,
        host="127.0.0.1",
        port=8080,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )
    mock.config.features.rate_limit = MagicMock()
    mock.config.features.policy = MagicMock()
    mock.config.features.style = MagicMock()
    mock.config.features.reflection = MagicMock()
    mock.config.features.compression = MagicMock()
    mock.config.features.handoff = MagicMock()
    mock.config.features.security = MagicMock()
    mock.config.features.web_search = MagicMock()
    mock.memory_store = MemoryStore(db)
    await mock.memory_store.create_table()
    mock.topic_store = TopicStore(db)
    mock.tool_registry = MagicMock()
    mock.tool_registry.list_names.return_value = []
    return mock


@pytest.fixture
def client(mock_app: MagicMock) -> TestClient:
    telegram_adapter = MagicMock()
    telegram_adapter._config = MagicMock(allowed_users=["12345"])
    telegram_adapter.send_message = AsyncMock(return_value="msg_1")

    web_config = WebConfig(
        enabled=True,
        auth_enabled=True,
        session_lifetime_hours=72,
        code_expiry_seconds=300,
        code_length=6,
    )

    auth_manager = AuthManager(
        adapters={"telegram": telegram_adapter},
        config=web_config,
    )

    ctx = WebContext(
        session_store=AsyncMock(),
        proposal_store=AsyncMock(),
        style_store=AsyncMock(),
        scheduler_store=AsyncMock(),
        trace_store=AsyncMock(),
        failure_store=AsyncMock(),
        workflow_store=AsyncMock(),
        execution_store=AsyncMock(),
        error_resolution_store=AsyncMock(),
        app=mock_app,
        auth_manager=auth_manager,
        user_store=AsyncMock(),
        topic_store=mock_app.topic_store,
    )
    set_web_context(ctx)

    app = create_web_app()
    app.add_middleware(
        AuthMiddleware,
        auth_manager=auth_manager,
        web_config=web_config,
    )
    return TestClient(app)


def _auth_token(client: TestClient) -> str:
    response = client.post("/api/auth/request-code", json={"platform": "telegram"})
    assert response.status_code == 200

    from hestia.web import context as ctx_mod

    ctx = ctx_mod._ctx
    assert ctx is not None
    code = list(ctx.auth_manager._pending_codes.keys())[0]
    response = client.post("/api/auth/verify-code", json={"code": code})
    assert response.status_code == 200
    return response.json()["token"]


class TestMemoryCurationRoutes:
    @pytest.mark.asyncio
    async def test_list_memories_includes_topics(self, client: TestClient):
        """GET /memory returns memories with topic_ids and scope flags."""
        token = _auth_token(client)

        # Seed data directly through stores.
        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        topic = await ctx.topic_store.get_or_create_topic("telegram", "12345", "food")
        await ctx.app.memory_store.save(
            content="Likes pizza",
            platform="telegram",
            platform_user="12345",
            topic_ids=[topic.id],
        )

        response = client.get(
            "/api/memory?platform=telegram&platform_user=12345&include_inactive=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1
        memory = data["memories"][0]
        assert memory["topic_ids"] == [topic.id]
        assert memory["is_global"] is False
        assert "is_pinned" in memory

    @pytest.mark.asyncio
    async def test_update_memory_scope_and_topics(self, client: TestClient):
        """PUT /memory/{id} updates scope and topic associations."""
        token = _auth_token(client)

        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        topic_a = await ctx.topic_store.get_or_create_topic("telegram", "12345", "a")
        topic_b = await ctx.topic_store.get_or_create_topic("telegram", "12345", "b")
        mem = await ctx.app.memory_store.save(
            content="Scoped to a",
            platform="telegram",
            platform_user="12345",
            topic_ids=[topic_a.id],
        )

        response = client.put(
            f"/api/memory/{mem.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"topic_ids": [topic_b.id]},
        )
        assert response.status_code == 200
        assert response.json()["memory"]["topic_ids"] == [topic_b.id]

    @pytest.mark.asyncio
    async def test_soft_delete_and_restore_memory(self, client: TestClient):
        """Soft-delete and restore endpoints toggle memory active state."""
        token = _auth_token(client)

        from hestia.web import context as ctx_mod

        ctx = ctx_mod._ctx
        assert ctx is not None
        mem = await ctx.app.memory_store.save(
            content="Delete me", platform="telegram", platform_user="12345"
        )

        response = client.post(
            f"/api/memory/{mem.id}/soft-delete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        response = client.get(
            "/api/memory?platform=telegram&platform_user=12345&include_inactive=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.json()["memories"][0]["is_active"] is False

        response = client.post(
            f"/api/memory/{mem.id}/restore",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["restored"] is True

        response = client.get(
            "/api/memory?platform=telegram&platform_user=12345",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(response.json()["memories"]) == 1


class TestTopicCurationRoutes:
    @pytest.mark.asyncio
    async def test_create_and_list_topics(self, client: TestClient):
        """POST /topics creates a topic; GET /topics lists it."""
        token = _auth_token(client)

        response = client.post(
            "/api/topics",
            headers={"Authorization": f"Bearer {token}"},
            json={"platform": "telegram", "platform_user": "12345", "name": "travel"},
        )
        assert response.status_code == 200
        topic_id = response.json()["topic"]["id"]

        response = client.get(
            "/api/topics?platform=telegram&platform_user=12345",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        topics = response.json()["topics"]
        assert len(topics) == 1
        assert topics[0]["name"] == "travel"
        assert topics[0]["id"] == topic_id

    @pytest.mark.asyncio
    async def test_rename_and_delete_topic(self, client: TestClient):
        """PUT /topics/{id} renames; DELETE /topics/{id} removes."""
        token = _auth_token(client)

        response = client.post(
            "/api/topics",
            headers={"Authorization": f"Bearer {token}"},
            json={"platform": "telegram", "platform_user": "12345", "name": "old"},
        )
        topic_id = response.json()["topic"]["id"]

        response = client.put(
            f"/api/topics/{topic_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "new"},
        )
        assert response.status_code == 200
        assert response.json()["topic"]["name"] == "new"

        response = client.delete(
            f"/api/topics/{topic_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        response = client.get(
            "/api/topics?platform=telegram&platform_user=12345",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.json()["topics"] == []
