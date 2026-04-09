#!/usr/bin/env python3
"""Calibration script for count_request accuracy.

Measures the ratio between count_request() estimates and actual prompt_tokens
from llama-server across various conversation shapes, then writes a correction
factor to docs/calibration.json for use by ContextBuilder.
"""

import asyncio
import json
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from hestia.core.inference import InferenceClient
from hestia.core.types import Message, ToolCall, ToolSchema


@dataclass
class CalibrationResult:
    shape: str
    predicted: int
    actual: int
    ratio: float


# Test conversation shapes
TEST_SHAPES: list[tuple[str, list[Message], list[ToolSchema]]] = [
    (
        "short_1user",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello!"),
        ],
        [],
    ),
    (
        "medium_5turns",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="What is 2+2?"),
            Message(role="assistant", content="4"),
            Message(role="user", content="What is 3+3?"),
            Message(role="assistant", content="6"),
            Message(role="user", content="What is 4+4?"),
        ],
        [],
    ),
    (
        "long_20turns",
        [
            Message(role="system", content="You are a helpful assistant."),
            *[msg for i in range(10) for msg in [
                Message(role="user", content=f"Question {i+1}?"),
                Message(role="assistant", content=f"Answer {i+1}."),
            ]],
            Message(role="user", content="Final question?"),
        ],
        [],
    ),
    (
        "with_tools",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="List the files."),
        ],
        [
            ToolSchema(
                type="function",
                function={
                    "name": "list_files",
                    "description": "List files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                    },
                },
            ),
            ToolSchema(
                type="function",
                function={
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                    },
                },
            ),
            ToolSchema(
                type="function",
                function={
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                },
            ),
        ],
    ),
    (
        "with_tool_result",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="List files"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id="call_1", name="list_files", arguments={"path": "/tmp"})
                ],
            ),
            Message(
                role="tool",
                content='["file1.txt", "file2.txt", "file3.txt"]',
                tool_call_id="call_1",
            ),
            Message(role="user", content="What's in file1?"),
        ],
        [],
    ),
    (
        "multi_tool_chain",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Check files and logs"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id="call_1", name="list_files", arguments={"path": "/tmp"}),
                    ToolCall(id="call_2", name="read_file", arguments={"path": "/var/log/syslog"}),
                ],
            ),
            Message(
                role="tool",
                content='["a.txt", "b.txt"]',
                tool_call_id="call_1",
            ),
            Message(
                role="tool",
                content="Log line 1\nLog line 2\nLog line 3",
                tool_call_id="call_2",
            ),
            Message(role="user", content="Any errors?"),
        ],
        [],
    ),
    (
        "long_content",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Here's a story: " + "Lorem ipsum " * 100),
            Message(role="assistant", content="Interesting story!"),
            Message(role="user", content="What do you think?"),
        ],
        [],
    ),
    (
        "system_heavy",
        [
            Message(
                role="system",
                content="You are a helpful assistant. " * 50 + "Be concise.",
            ),
            Message(role="user", content="Hi"),
        ],
        [],
    ),
    (
        "mixed_tools_and_content",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Do task 1"),
            Message(
                role="assistant",
                content="Result of task 1",
                tool_calls=[ToolCall(id="call_1", name="task1", arguments={})],
            ),
            Message(role="tool", content="Task 1 output", tool_call_id="call_1"),
            Message(role="assistant", content="Task 1 complete."),
            Message(role="user", content="Now do task 2"),
            Message(
                role="assistant",
                content="Result of task 2",
                tool_calls=[ToolCall(id="call_2", name="task2", arguments={})],
            ),
            Message(role="tool", content="Task 2 output", tool_call_id="call_2"),
            Message(role="user", content="Summarize both tasks."),
        ],
        [
            ToolSchema(
                type="function",
                function={
                    "name": "task1",
                    "description": "Do task 1",
                    "parameters": {"type": "object", "properties": {}},
                },
            ),
            ToolSchema(
                type="function",
                function={
                    "name": "task2",
                    "description": "Do task 2",
                    "parameters": {"type": "object", "properties": {}},
                },
            ),
        ],
    ),
    (
        "minimal",
        [
            Message(role="user", content="Hi"),
        ],
        [],
    ),
]


async def calibrate() -> list[CalibrationResult]:
    """Run calibration against llama-server."""
    client = InferenceClient("http://localhost:8001", "Qwen3.5-9B-UD-Q4_K_XL.gguf")
    results: list[CalibrationResult] = []

    try:
        for shape_name, messages, tools in TEST_SHAPES:
            print(f"Testing {shape_name}...", end=" ", flush=True)

            # Get predicted count
            predicted = await client.count_request(messages, tools)

            # Get actual count from server (use max_tokens=1 for speed)
            response = await client.chat(
                messages=messages,
                tools=tools if tools else None,
                max_tokens=1,  # Minimal generation for speed
            )
            actual = response.prompt_tokens

            ratio = predicted / actual if actual > 0 else 0.0
            result = CalibrationResult(
                shape=shape_name,
                predicted=predicted,
                actual=actual,
                ratio=ratio,
            )
            results.append(result)
            print(f"predicted={predicted}, actual={actual}, ratio={ratio:.2f}")

    finally:
        await client.close()

    return results


def analyze(results: list[CalibrationResult]) -> dict:
    """Compute statistics from calibration results."""
    ratios = [r.ratio for r in results]
    return {
        "mean_ratio": statistics.mean(ratios),
        "stdev": statistics.stdev(ratios) if len(ratios) > 1 else 0.0,
        "min": min(ratios),
        "max": max(ratios),
        "median": statistics.median(ratios),
        "n_samples": len(ratios),
    }


def print_table(results: list[CalibrationResult]) -> None:
    """Print formatted results table."""
    print("\n" + "=" * 70)
    print(f"{'Shape':<25} {'Predicted':>10} {'Actual':>10} {'Ratio':>10}")
    print("-" * 70)
    for r in results:
        print(f"{r.shape:<25} {r.predicted:>10} {r.actual:>10} {r.ratio:>10.2f}")
    print("=" * 70)


def print_stats(stats: dict) -> None:
    """Print aggregate statistics."""
    print(f"\nAggregate Statistics:")
    print(f"  Mean ratio:   {stats['mean_ratio']:.3f}")
    print(f"  Stdev:        {stats['stdev']:.3f}")
    print(f"  Min:          {stats['min']:.3f}")
    print(f"  Max:          {stats['max']:.3f}")
    print(f"  Median:       {stats['median']:.3f}")
    print(f"  Samples:      {stats['n_samples']}")


def save_calibration(
    results: list[CalibrationResult],
    stats: dict,
    output_path: Path,
) -> None:
    """Save calibration data to JSON file."""
    calibration_data = {
        "timestamp": datetime.now().isoformat(),
        "model": "Qwen3.5-9B-UD-Q4_K_XL.gguf",
        "base_url": "http://localhost:8001",
        "correction_factor": stats["mean_ratio"],
        "statistics": stats,
        "measurements": [asdict(r) for r in results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(calibration_data, f, indent=2)

    print(f"\nCalibration data written to: {output_path}")


def main() -> int:
    """Run calibration and save results."""
    print("Hestia Token Count Calibration")
    print("=" * 50)
    print(f"Server: http://localhost:8001")
    print(f"Model:  Qwen3.5-9B-UD-Q4_K_XL.gguf")
    print()

    # Check server health
    async def check_health():
        client = InferenceClient("http://localhost:8001", "test")
        try:
            health = await client.health()
            return health.get("status") == "ok"
        except Exception as e:
            print(f"Server health check failed: {e}")
            return False
        finally:
            await client.close()

    if not asyncio.run(check_health()):
        print("\nERROR: Cannot connect to llama-server at localhost:8001")
        print("Make sure the server is running before running calibration.")
        return 1

    print("Server is healthy. Running calibration...\n")

    # Run calibration
    results = asyncio.run(calibrate())

    # Analyze and display
    stats = analyze(results)
    print_table(results)
    print_stats(stats)

    # Save to file
    output_path = Path("docs/calibration.json")
    save_calibration(results, stats, output_path)

    print(f"\nCorrection factor for ContextBuilder: {stats['mean_ratio']:.3f}")
    print("\nAdd this to your ADR:")
    print(f"  Measured mean ratio of {stats['mean_ratio']:.2f} ± {stats['stdev']:.2f}")
    print(f"  across {stats['n_samples']} shapes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
