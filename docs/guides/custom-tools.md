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
- Use typed arguments. Hestia generates a JSON schema from the function signature.
- Return strings. Complex results should be saved as artifacts and a handle returned.
- Handle errors gracefully. Uncaught exceptions become tool-error messages in the conversation.
