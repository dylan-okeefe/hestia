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
