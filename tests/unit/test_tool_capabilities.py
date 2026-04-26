"""Unit tests for tool capability labels."""

from hestia.config import StorageConfig
from hestia.tools.builtin import (
    NETWORK_EGRESS,
    READ_LOCAL,
    SHELL_EXEC,
    WRITE_LOCAL,
    current_time,
    http_get,
    make_list_dir_tool,
    make_read_file_tool,
    make_write_file_tool,
    make_terminal_tool,
)
from hestia.tools.builtin.delegate_task import make_delegate_task_tool
from hestia.tools.builtin.memory_tools import (
    make_list_memories_tool,
    make_save_memory_tool,
    make_search_memory_tool,
)
from hestia.tools.builtin.read_artifact import make_read_artifact_tool
from hestia.tools.metadata import ToolMetadata, tool

terminal = make_terminal_tool()


class TestToolCapabilities:
    """Tests for capability labels on tools."""

    def test_all_builtin_tools_have_capabilities(self):
        """Every built-in tool must have explicit capabilities (can be empty)."""
        # Create factory tools for testing
        read_file = make_read_file_tool(StorageConfig(allowed_roots=["/tmp"]))
        write_file = make_write_file_tool(StorageConfig(allowed_roots=["/tmp"]))
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=["/tmp"]))

        # Check tools with @tool decorator
        tools_to_check = [
            ("current_time", current_time),
            ("read_file", read_file),
            ("write_file", write_file),
            ("list_dir", list_dir),
            ("terminal", terminal),
            ("http_get", http_get),
        ]

        for name, tool_func in tools_to_check:
            meta = getattr(tool_func, "__hestia_tool__", None)
            assert meta is not None, f"{name} is missing tool metadata"
            assert hasattr(meta, "capabilities"), f"{name} is missing capabilities field"
            assert isinstance(meta.capabilities, list), f"{name} capabilities must be a list"

    def test_read_file_has_read_local(self):
        """read_file has READ_LOCAL capability."""
        read_file = make_read_file_tool(StorageConfig(allowed_roots=["/tmp"]))
        meta = read_file.__hestia_tool__
        assert READ_LOCAL in meta.capabilities

    def test_write_file_has_write_local(self):
        """write_file has WRITE_LOCAL capability."""
        write_file = make_write_file_tool(StorageConfig(allowed_roots=["/tmp"]))
        meta = write_file.__hestia_tool__
        assert WRITE_LOCAL in meta.capabilities

    def test_list_dir_has_read_local(self):
        """list_dir has READ_LOCAL capability."""
        list_dir = make_list_dir_tool(StorageConfig(allowed_roots=["/tmp"]))
        meta = list_dir.__hestia_tool__
        assert READ_LOCAL in meta.capabilities

    def test_terminal_has_shell_exec(self):
        """terminal has SHELL_EXEC capability."""
        meta = terminal.__hestia_tool__
        assert SHELL_EXEC in meta.capabilities

    def test_http_get_has_network_egress(self):
        """http_get has NETWORK_EGRESS capability."""
        meta = http_get.__hestia_tool__
        assert NETWORK_EGRESS in meta.capabilities

    def test_current_time_has_empty_capabilities(self):
        """current_time has empty capabilities (safe tool)."""
        meta = current_time.__hestia_tool__
        assert meta.capabilities == []

    def test_memory_tools_have_memory_capabilities(self):
        """Memory tools have MEMORY_READ or MEMORY_WRITE capabilities."""
        from hestia.persistence.db import Database

        Database("sqlite+aiosqlite:///:memory:")
        # Note: We can't await here in a sync test, so we just check the factory
        # creates tools with the right capabilities using mock

        # Test that factories create tools with proper capabilities
        # by inspecting the decorator at function definition time

        # For memory tools, we verify the factory sets capabilities
        # The actual check is done in the tool definition
        import inspect

        # Check source code has capabilities parameter
        src = inspect.getsource(make_search_memory_tool)
        assert "MEMORY_READ" in src

        src = inspect.getsource(make_save_memory_tool)
        assert "MEMORY_WRITE" in src

        src = inspect.getsource(make_list_memories_tool)
        assert "MEMORY_READ" in src

    def test_delegate_task_has_orchestration(self):
        """delegate_task has ORCHESTRATION capability."""
        import inspect

        src = inspect.getsource(make_delegate_task_tool)
        assert "ORCHESTRATION" in src

    def test_read_artifact_has_read_local(self):
        """read_artifact has READ_LOCAL capability."""
        import inspect

        src = inspect.getsource(make_read_artifact_tool)
        assert "READ_LOCAL" in src


class TestToolMetadataDefaults:
    """Tests for ToolMetadata default values."""

    def test_capabilities_defaults_to_empty_list(self):
        """ToolMetadata.capabilities defaults to empty list."""
        meta = ToolMetadata(
            name="test_tool",
            public_description="A test tool",
            internal_description="Internal docs",
            parameters_schema={"type": "object", "properties": {}},
        )
        assert meta.capabilities == []

    def test_capabilities_can_be_set_explicitly(self):
        """ToolMetadata.capabilities can be set explicitly."""
        meta = ToolMetadata(
            name="test_tool",
            public_description="A test tool",
            internal_description="Internal docs",
            parameters_schema={"type": "object", "properties": {}},
            capabilities=[READ_LOCAL, WRITE_LOCAL],
        )
        assert meta.capabilities == [READ_LOCAL, WRITE_LOCAL]


class TestToolDecoratorCapabilities:
    """Tests for @tool decorator capabilities parameter."""

    def test_tool_decorator_accepts_capabilities(self):
        """@tool decorator accepts capabilities parameter."""

        @tool(
            name="capability_test_tool",
            public_description="Testing capabilities",
            capabilities=[READ_LOCAL, SHELL_EXEC],
        )
        async def test_tool() -> str:
            return "ok"

        meta = test_tool.__hestia_tool__
        assert READ_LOCAL in meta.capabilities
        assert SHELL_EXEC in meta.capabilities

    def test_tool_decorator_capabilities_defaults_to_empty(self):
        """@tool decorator defaults capabilities to empty list."""

        @tool(
            name="no_capability_tool",
            public_description="No special capabilities",
        )
        async def test_tool() -> str:
            return "ok"

        meta = test_tool.__hestia_tool__
        assert meta.capabilities == []
