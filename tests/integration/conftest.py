# mypy: disable-error-code="no-untyped-def,import-not-found"
"""Shared fixtures for integration tests."""

import pytest
from helpers import FakeInferenceClient, FakePolicyEngine

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.memory.store import MemoryStore
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.tools.registry import ToolRegistry
from hestia.config import StorageConfig


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()

    s = SessionStore(db)
    yield s
    await db.close()


@pytest.fixture
async def memory_store(store):
    """Create a MemoryStore bound to the same database."""
    ms = MemoryStore(store._db)
    await ms.create_table()
    yield ms
    # Teardown: delete all L11 test memories
    memories = await ms.list_memories(tag="e2e_hestia_l11")
    for mem in memories:
        await ms.delete(mem.id)


@pytest.fixture
def artifact_store(tmp_path):
    """Artifact store in temp directory."""
    return ArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def file_sandbox(tmp_path):
    """Sandbox directory for file tool tests."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return str(sandbox)


@pytest.fixture
def fake_inference():
    """Fake inference client."""
    return FakeInferenceClient()


@pytest.fixture
def fake_policy():
    """Fake policy engine."""
    return FakePolicyEngine()


@pytest.fixture
def context_builder(fake_inference, fake_policy):
    """Context builder with no calibration."""
    return ContextBuilder(fake_inference, fake_policy, body_factor=1.0)


@pytest.fixture
def responses():
    """List to capture responses."""
    return []


@pytest.fixture
def respond_callback(responses):
    """Callback that captures responses."""

    async def callback(response):
        responses.append(response)

    return callback


@pytest.fixture
def tool_registry(artifact_store, memory_store, file_sandbox):
    """Tool registry with all built-in tools except delegate_task."""
    registry = ToolRegistry(artifact_store)

    from hestia.tools.builtin import current_time, http_get, terminal
    from hestia.tools.builtin.list_dir import make_list_dir_tool
    from hestia.tools.builtin.memory_tools import (
        make_list_memories_tool,
        make_save_memory_tool,
        make_search_memory_tool,
    )
    from hestia.tools.builtin.read_artifact import make_read_artifact_tool
    from hestia.tools.builtin.read_file import make_read_file_tool
    from hestia.tools.builtin.write_file import make_write_file_tool

    registry.register(current_time)
    registry.register(http_get)
    registry.register(terminal)
    registry.register(make_read_file_tool(StorageConfig(allowed_roots=[file_sandbox])))
    registry.register(make_list_dir_tool(StorageConfig(allowed_roots=[file_sandbox])))
    registry.register(make_write_file_tool(StorageConfig(allowed_roots=[file_sandbox])))
    registry.register(make_read_artifact_tool(artifact_store))
    registry.register(make_save_memory_tool(memory_store))
    registry.register(make_list_memories_tool(memory_store))
    registry.register(make_search_memory_tool(memory_store))

    return registry