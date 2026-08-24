"""Unit tests for ToolRegistry direct tool schemas."""

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolRegistry


@pytest.fixture
def registry(tmp_path):
    """Create a ToolRegistry with temp artifact store."""
    store = ArtifactStore(root=tmp_path)
    return ToolRegistry(store)


@tool(
    name="greet",
    public_description="Greet someone by name",
    parameters_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
async def greet(name: str) -> str:
    return f"Hello, {name}!"


class TestDirectToolSchemas:
    """Tests for direct_tool_schemas()."""

    def test_returns_schema_for_meta_tools(self, registry):
        """meta_tool_schemas returns schemas for the three meta-tools."""
        registry.register(greet)

        schemas = registry.meta_tool_schemas()
        names = [s.function.name for s in schemas]

        assert "list_tools" in names
        assert "describe_tool" in names
        assert "call_tool" in names
        assert len(schemas) == 3

    def test_meta_schema_names_are_fixed(self, registry):
        """Meta-tool schema names are always the three meta-tools."""
        registry.register(greet)

        schemas = registry.meta_tool_schemas()
        names = {s.function.name for s in schemas}

        assert names == {"list_tools", "describe_tool", "call_tool"}

    def test_call_tool_schema_teaches_chunked_writes(self, registry):
        """call_tool description tells the model to chunk large file writes."""
        registry.register(greet)
        schemas = {s.function.name: s for s in registry.meta_tool_schemas()}
        desc = schemas["call_tool"].function.description
        assert "50000 characters" in desc
        assert "write_file" in desc
        assert "append_to_file" in desc

    def test_write_file_schema_teaches_chunked_writes(self):
        """The write_file tool description teaches the raised character limit."""
        from hestia.config import StorageConfig
        from hestia.tools.builtin.write_file import make_write_file_tool

        tool = make_write_file_tool(StorageConfig(allowed_roots=[]))
        meta = tool.__hestia_tool__
        assert "several thousand characters" in meta.public_description
        assert "append_to_file" in meta.parameters_schema["properties"]["content"]["description"]

    def test_append_to_file_schema_teaches_chunked_writes(self):
        """The append_to_file tool description teaches the 2000-character limit."""
        from hestia.config import StorageConfig
        from hestia.tools.builtin.append_to_file import make_append_to_file_tool

        tool = make_append_to_file_tool(StorageConfig(allowed_roots=[]))
        meta = tool.__hestia_tool__
        assert "2000 characters" in meta.public_description
        assert "write_file" in meta.public_description
