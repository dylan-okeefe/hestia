# Custom Tools

Hestia's built-in tools cover filesystem, memory, email, network, and orchestration, but the real power comes from adding your own.

## The `@tool` decorator

Import `tool` from `hestia.tools.metadata`, decorate an async function, and declare its capabilities:

```python
from hestia.tools.metadata import tool

@tool(
    name="weather",
    public_description="Get weather for a location",
    capabilities=["network_egress"],
)
async def get_weather(location: str) -> str:
    return f"Weather for {location}: sunny, 22C"
```

Register it at config build time and the model sees it in `list_tools`.

## Capability labels

Every tool must declare what it can do. Available capabilities:

- `read_local` — reads files or directories
- `write_local` — writes or mutates files
- `shell_exec` — runs shell commands
- `network_egress` — makes outbound HTTP requests
- `memory_read` — searches or lists memories
- `memory_write` — saves or deletes memories
- `orchestration` — spawns subagents or controls scheduling

The policy engine uses these labels to restrict access by context. For example, subagents cannot use `shell_exec` tools, and scheduled tasks cannot use `write_local` tools by default.

## Best practices

- Keep descriptions concise. The model sees `public_description` in `list_tools`.
- Declare an explicit `parameters_schema`. The `@tool` decorator does not auto-generate a schema from the function signature.
- Return strings. Complex results should be saved as artifacts and a handle returned.
- Handle errors gracefully. Uncaught exceptions become tool-error messages in the conversation.

## External tool modules

You can package custom tools in a separate Python package and load them at runtime without modifying Hestia.

### 1. Create a package with `setup` and `register` hooks

Your package must expose a callable named `register` that accepts a `ToolRegistry`. It may also expose an optional `setup(context)` hook that runs before `register`; the context exposes `db` and `config` so your module can create its own stores or tables.

```python
# my_private_tools/__init__.py
from hestia.tools.external_context import ExternalToolModuleContext
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolRegistry

# Module-level state created in setup()
_store: dict[str, str] = {}


@tool(
    name="deploy_internal_service",
    public_description="Deploy an internal service via the company API",
    capabilities=["network_egress"],
)
async def deploy_internal_service(service: str) -> str:
    ...


@tool(
    name="lookup_private_note",
    public_description="Look up a private note stored by this module.",
    capabilities=["memory_read"],
)
async def lookup_private_note(key: str) -> str:
    return _store.get(key, "")


def setup(context: ExternalToolModuleContext) -> None:
    """Create module-owned persistence before registering tools."""
    _store["welcome"] = "external module is set up"


def register(registry: ToolRegistry) -> None:
    registry.register(deploy_internal_service)
    registry.register(lookup_private_note)
```

### 2. Add the dotted path to config

```python
config = HestiaConfig(
    extra_tool_modules=["my_private_tools"],
)
```

Or via environment variable:

```bash
export HESTIA_EXTRA_TOOL_MODULES='["my_private_tools"]'
```

### 3. Restart Hestia

On startup, Hestia imports each configured module and calls `register(registry)` after all built-in tools are registered.

### Trust warning

External tools are **not** sandboxed or exempt from Hestia's capability system. They share the same `CapabilityGate` and `DefaultPolicyEngine` filtering as built-in tools. If your tool declares `shell_exec` or `write_local`, it will be denied in subagent and scheduler sessions by default, and the capability gate will still enforce confirmation and channel rules. Choose capability labels carefully.

If your module implements `setup(context)`, Hestia passes it a live database handle (`context.db`). This is a wide trust grant: the module can read or mutate any table in the database. Only list modules you fully control in `extra_tool_modules`, and avoid sharing that config across untrusted deployments.

