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

    def test_returns_schema_for_every_registered_tool(self, registry):
        """direct_tool_schemas returns a ToolSchema for each registered tool."""
        registry.register(greet)

        schemas = registry.direct_tool_schemas()
        names = [s.function.name for s in schemas]

        # Built-ins are auto-registered
        assert "list_tools" in names
        assert "describe_tool" in names
        assert "greet" in names
        assert len(schemas) == 3

    def test_schema_names_match_registered_names(self, registry):
        """Schema names correspond to registered tool metadata."""
        registry.register(greet)

        schemas = registry.direct_tool_schemas()
        names = {s.function.name for s in schemas}

        assert names == {"list_tools", "describe_tool", "greet"}
