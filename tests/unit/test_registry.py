"""Unit tests for ToolRegistry."""

from types import SimpleNamespace

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolNotFoundError, ToolRegistry


@pytest.fixture
def registry(tmp_path):
    """Create a ToolRegistry with temp artifact store."""
    store = ArtifactStore(root=tmp_path)
    return ToolRegistry(store)


# --- Test fixtures: decorated tools ---


@tool(
    name="greet",
    public_description="Greet someone by name",
    parameters_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
    tags=["utility"],
)
async def greet(name: str) -> str:
    return f"Hello, {name}!"


@tool(
    name="add",
    public_description="Add two numbers",
    parameters_schema={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    },
    tags=["math"],
)
async def add(a: float, b: float) -> float:
    return a + b


@tool(
    name="failing_tool",
    public_description="Always fails",
    parameters_schema={"type": "object", "properties": {}},
)
async def failing_tool() -> str:
    raise ValueError("Intentional failure")


class TestRegistration:
    """Tests for tool registration."""

    def test_register_decorated_function(self, registry):
        """Register a @tool-decorated function."""
        registry.register(greet)
        assert "greet" in registry.list_names()

    def test_register_non_decorated_raises(self, registry):
        """Registering non-decorated function raises ValueError."""

        async def not_a_tool():
            pass

        with pytest.raises(ValueError, match="not decorated"):
            registry.register(not_a_tool)

    def test_double_register_raises(self, registry):
        """Registering same tool twice raises ValueError."""
        registry.register(greet)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(greet)

    def test_register_module(self, registry):
        """register_module finds all @tools in a module."""
        # Create a mock module with our test tools
        module = SimpleNamespace()
        module.greet = greet
        module.add = add
        module.not_a_tool = lambda: None  # Not decorated

        registry.register_module(module)

        assert "greet" in registry.list_names()
        assert "add" in registry.list_names()
        assert len(registry.list_names()) == 2


class TestListAndDescribe:
    """Tests for listing and describing tools."""

    def test_list_names_sorted(self, registry):
        """list_names returns sorted list."""
        registry.register(add)
        registry.register(greet)

        names = registry.list_names()
        assert names == ["add", "greet"]  # Alphabetical

    def test_list_names_with_tag(self, registry):
        """list_names filters by tag."""
        registry.register(greet)  # utility tag
        registry.register(add)  # math tag

        assert registry.list_names(tag="utility") == ["greet"]
        assert registry.list_names(tag="math") == ["add"]
        assert registry.list_names(tag="nonexistent") == []

    def test_describe_returns_metadata(self, registry):
        """describe returns ToolMetadata."""
        registry.register(greet)

        meta = registry.describe("greet")
        assert meta.name == "greet"
        assert meta.public_description == "Greet someone by name"
        assert "utility" in meta.tags

    def test_describe_missing_raises(self, registry):
        """describe raises ToolNotFoundError for missing tool."""
        with pytest.raises(ToolNotFoundError):
            registry.describe("nonexistent")


class TestCalling:
    """Tests for tool dispatch."""

    @pytest.mark.asyncio
    async def test_call_tool(self, registry):
        """call dispatches to handler and returns result."""
        registry.register(greet)

        result = await registry.call("greet", {"name": "Alice"})
        assert result.status == "ok"
        assert result.content == "Hello, Alice!"
        assert result.artifact_handle is None
        assert not result.truncated

    @pytest.mark.asyncio
    async def test_call_with_numbers(self, registry):
        """call works with numeric arguments."""
        registry.register(add)

        result = await registry.call("add", {"a": 1.5, "b": 2.5})
        assert result.status == "ok"
        assert result.content == "4.0"

    @pytest.mark.asyncio
    async def test_call_error_handling(self, registry):
        """call returns error status on exception."""
        registry.register(failing_tool)

        result = await registry.call("failing_tool", {})
        assert result.status == "error"
        assert "Intentional failure" in result.content

    @pytest.mark.asyncio
    async def test_call_missing_tool_raises(self, registry):
        """call raises ToolNotFoundError for missing tool."""
        with pytest.raises(ToolNotFoundError):
            await registry.call("nonexistent", {})


class TestAutoArtifact:
    """Tests for auto-promotion to artifacts."""

    @pytest.mark.asyncio
    async def test_small_result_inline(self, registry):
        """Small results are returned inline."""
        registry.register(greet)

        result = await registry.call("greet", {"name": "Short"})
        assert result.artifact_handle is None
        assert "stored as artifact" not in result.content

    @pytest.mark.asyncio
    async def test_large_result_becomes_artifact(self, registry, tmp_path):
        """Large results (> max_inline_chars) become artifacts."""

        # Create a tool with low threshold
        @tool(
            name="large_output",
            public_description="Returns large output",
            parameters_schema={"type": "object", "properties": {}},
            max_inline_chars=10,  # Very low for testing
        )
        async def large_output() -> str:
            return "x" * 100

        registry.register(large_output)

        result = await registry.call("large_output", {})
        assert result.artifact_handle is not None
        assert result.artifact_handle.startswith("art_")
        assert "stored as artifact" in result.content
        assert "showing first" in result.content


class TestMetaTools:
    """Tests for meta-tool operations."""

    def test_meta_tool_schemas(self, registry):
        """meta_tool_schemas returns list_tools and call_tool."""
        schemas = registry.meta_tool_schemas()
        assert len(schemas) == 2

        names = [s.function.name for s in schemas]
        assert "list_tools" in names
        assert "call_tool" in names

    @pytest.mark.asyncio
    async def test_meta_list_tools(self, registry):
        """meta_list_tools returns formatted tool list."""
        registry.register(greet)
        registry.register(add)

        output = await registry.meta_list_tools()
        assert "greet" in output
        assert "add" in output
        assert "Greet someone" in output
        assert "Add two numbers" in output

    @pytest.mark.asyncio
    async def test_meta_list_tools_empty(self, registry):
        """meta_list_tools handles empty registry."""
        output = await registry.meta_list_tools()
        assert output == "(no tools)"

    @pytest.mark.asyncio
    async def test_meta_list_tools_with_tag(self, registry):
        """meta_list_tools respects tag filter."""
        registry.register(greet)  # utility
        registry.register(add)  # math

        output = await registry.meta_list_tools(tag="utility")
        assert "greet" in output
        assert "add" not in output

    @pytest.mark.asyncio
    async def test_meta_list_tools_with_detail(self, registry):
        """meta_list_tools includes schemas when detail=true."""
        registry.register(greet)

        output = await registry.meta_list_tools(detail=True)
        assert "greet" in output
        assert "schema:" in output
        assert "name" in output  # greet's parameters_schema has 'name'

    @pytest.mark.asyncio
    async def test_meta_call_tool(self, registry):
        """meta_call_tool dispatches correctly."""
        registry.register(greet)

        result = await registry.meta_call_tool("greet", {"name": "Bob"})
        assert result.status == "ok"
        assert "Bob" in result.content
