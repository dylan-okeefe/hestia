"""Phase 1b integration test — proto-orchestrator.

This test wires ContextBuilder + ToolRegistry + InferenceClient together
without the full orchestrator (which is Phase 1c). It proves the pieces
compose correctly by driving a real inference call through the tool registry.
"""

from datetime import datetime

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.policy.default import DefaultPolicyEngine
from hestia.tools.builtin import current_time, terminal
from hestia.tools.builtin.read_artifact import make_read_artifact_tool
from hestia.tools.builtin.read_file import make_read_file_tool
from hestia.tools.registry import ToolRegistry

SYSTEM_PROMPT = """You are a helpful personal assistant. You have access to tools for:
- current_time: Get the current time
- read_file: Read a file's contents
- terminal: Run shell commands
- read_artifact: Read artifact content by handle

Use list_tools to discover tools, then call_tool to invoke them.
When asked to list files, use the terminal tool with 'ls'.
Be concise."""


@pytest.mark.asyncio
async def test_proto_orchestrator_uses_terminal_tool(tmp_path):
    """
    Ask the model: 'List the files in /tmp and tell me how many there are.'

    Expect it to:
    1. Call list_tools (optional)
    2. Call call_tool(name='terminal', arguments={'command': 'ls /tmp'})
    3. Produce a final answer with a count
    """
    # Setup
    inference = InferenceClient("http://localhost:8001", "Qwen3.5-9B-UD-Q4_K_XL.gguf")
    store = ArtifactStore(root=tmp_path / "artifacts")
    registry = ToolRegistry(store)

    # Register built-in tools
    registry.register(current_time)
    registry.register(make_read_file_tool(["/tmp"]))
    registry.register(terminal)
    registry.register(make_read_artifact_tool(store))

    # Load calibration and create context builder
    policy = DefaultPolicyEngine(ctx_window=8192)
    builder = ContextBuilder.from_calibration_file(inference, policy)

    # Create a session
    session = Session(
        id="test_integration",
        platform="test",
        platform_user="tester",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )

    # Initial state
    history: list[Message] = []
    user_msg = Message(
        role="user",
        content="List the files in /tmp and tell me how many there are.",
    )
    tools = registry.meta_tool_schemas()

    # Build initial context using ContextBuilder
    built = await builder.build(
        session=session,
        history=history,
        new_user_message=user_msg,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
    )

    # Loop: chat → dispatch → repeat, max 5 iterations
    terminal_was_called = False
    final_answer = ""
    messages_for_chat = built.messages

    for _ in range(5):
        # Get model response
        response = await inference.chat(
            messages=messages_for_chat,
            tools=tools,
            max_tokens=3000,
            reasoning_budget=2048,
        )

        if response.tool_calls:
            # Model wants to use tools
            history.append(
                Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )
            )

            # Dispatch each tool call
            for tc in response.tool_calls:
                if tc.name == "list_tools":
                    result_content = await registry.meta_list_tools(**tc.arguments)
                    history.append(
                        Message(
                            role="tool",
                            content=result_content,
                            tool_call_id=tc.id,
                        )
                    )
                elif tc.name == "call_tool":
                    result = await registry.meta_call_tool(**tc.arguments)
                    history.append(
                        Message(
                            role="tool",
                            content=result.content,
                            tool_call_id=tc.id,
                        )
                    )

                    # Track if terminal was called
                    if tc.arguments.get("name") == "terminal":
                        terminal_was_called = True
                else:
                    # Unknown meta-tool
                    history.append(
                        Message(
                            role="tool",
                            content=f"Unknown tool: {tc.name}",
                            tool_call_id=tc.id,
                        )
                    )

            # For subsequent iterations, use system + first user + history
            # We must include the first user message for the chat template
            messages_for_chat = [
                Message(role="system", content=SYSTEM_PROMPT),
                user_msg,  # First/only user message
                *history,
            ]
            continue

        # No tool calls: this is the final answer
        final_answer = response.content or ""
        break
    else:
        # Loop exhausted without final answer
        pytest.fail("Model never produced a final answer in 5 iterations")

    # Assertions
    # 1. Terminal was called at least once
    assert terminal_was_called, "Model should have called terminal tool"

    # 2. Final answer exists and contains digits (a count)
    assert final_answer, "Model should have produced a final answer"
    assert any(c.isdigit() for c in final_answer), (
        f"Expected a count in the answer, got: {final_answer[:200]}"
    )

    # Cleanup
    await inference.close()
