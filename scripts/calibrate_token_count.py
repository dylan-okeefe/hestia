#!/usr/bin/env python3
"""Calibration script for count_request accuracy.

Measures TWO separate calibration values:
1. body_factor: ratio of predicted/actual for message body only (no tools)
2. meta_tool_overhead_tokens: constant overhead of including meta-tools

This split is necessary because the client-side tokenization of JSON tool schemas
differs significantly from the server's chat-template expansion. Hestia always
uses the same two meta-tools, so their overhead is a constant.

New budget formula:
    corrected = int(predicted_body / body_factor) + meta_tool_overhead_tokens

Where predicted_body is count_request(messages, tools=[]).
"""

import asyncio
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from hestia.core.inference import InferenceClient
from hestia.core.types import FunctionSchema, Message, ToolSchema


@dataclass
class BodyCalibrationResult:
    shape: str
    predicted: int
    actual: int
    ratio: float


# Test conversation shapes for body calibration (NO tools)
BODY_TEST_SHAPES: list[tuple[str, list[Message]]] = [
    (
        "short_1user",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello!"),
        ],
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
    ),
    (
        "long_20turns",
        [
            Message(role="system", content="You are a helpful assistant."),
            *[
                msg
                for i in range(10)
                for msg in [
                    Message(role="user", content=f"Question {i + 1}?"),
                    Message(role="assistant", content=f"Answer {i + 1}."),
                ]
            ],
            Message(role="user", content="Final question?"),
        ],
    ),
    (
        "long_content",
        [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Here's a story: " + "Lorem ipsum " * 100),
        ],
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
    ),
    (
        "minimal",
        [
            Message(role="user", content="Hi"),
        ],
    ),
]

# The meta-tools Hestia always sends
META_TOOLS = [
    ToolSchema(
        type="function",
        function=FunctionSchema(
            name="list_tools",
            description="List all available tools.",
            parameters={
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                },
            },
        ),
    ),
    ToolSchema(
        type="function",
        function=FunctionSchema(
            name="call_tool",
            description="Invoke a tool by name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["name", "arguments"],
            },
        ),
    ),
]


async def calibrate_body_factor(client: InferenceClient) -> tuple[float, list[BodyCalibrationResult]]:
    """Measure body_factor on tool-free requests."""
    results: list[BodyCalibrationResult] = []

    print("Measuring body_factor (tool-free requests)...")
    for shape_name, messages in BODY_TEST_SHAPES:
        print(f"  Testing {shape_name}...", end=" ", flush=True)

        # Get predicted count (NO tools)
        predicted = await client.count_request(messages, tools=[])

        # Get actual count from server
        response = await client.chat(
            messages=messages,
            tools=None,
            max_tokens=1,  # Minimal for speed
        )
        actual = response.prompt_tokens

        ratio = predicted / actual if actual > 0 else 0.0
        result = BodyCalibrationResult(
            shape=shape_name,
            predicted=predicted,
            actual=actual,
            ratio=ratio,
        )
        results.append(result)
        print(f"predicted={predicted}, actual={actual}, ratio={ratio:.2f}")

    # Calculate statistics
    ratios = [r.ratio for r in results]
    body_factor = statistics.mean(ratios)

    return body_factor, results


async def calibrate_meta_tool_overhead(client: InferenceClient) -> tuple[int, list[int]]:
    """Measure the constant overhead of meta-tools."""
    print("\nMeasuring meta_tool_overhead_tokens...")

    # Simple test message
    messages = [Message(role="user", content="Hello")]

    measurements: list[int] = []
    for i in range(3):
        print(f"  Measurement {i + 1}/3...", end=" ", flush=True)

        # Without tools
        response_no_tools = await client.chat(
            messages=messages,
            tools=None,
            max_tokens=1,
        )
        tokens_no_tools = response_no_tools.prompt_tokens

        # With meta-tools
        response_with_tools = await client.chat(
            messages=messages,
            tools=META_TOOLS,
            max_tokens=1,
        )
        tokens_with_tools = response_with_tools.prompt_tokens

        overhead = tokens_with_tools - tokens_no_tools
        measurements.append(overhead)
        print(f"no_tools={tokens_no_tools}, with_tools={tokens_with_tools}, overhead={overhead}")

    meta_tool_overhead = int(statistics.mean(measurements))
    return meta_tool_overhead, measurements


def print_body_results(results: list[BodyCalibrationResult]) -> dict:
    """Print body calibration table and return statistics."""
    print("\n" + "=" * 70)
    print(f"{'Shape':<20} {'Predicted':>10} {'Actual':>10} {'Ratio':>10}")
    print("-" * 70)
    for r in results:
        print(f"{r.shape:<20} {r.predicted:>10} {r.actual:>10} {r.ratio:>10.2f}")
    print("=" * 70)

    ratios = [r.ratio for r in results]
    stats = {
        "mean": statistics.mean(ratios),
        "stdev": statistics.stdev(ratios) if len(ratios) > 1 else 0.0,
        "min": min(ratios),
        "max": max(ratios),
        "median": statistics.median(ratios),
        "n_samples": len(ratios),
    }

    print(f"\nBody Factor Statistics:")
    print(f"  Mean:   {stats['mean']:.3f}")
    print(f"  Stdev:  {stats['stdev']:.3f}")
    print(f"  Min:    {stats['min']:.3f}")
    print(f"  Max:    {stats['max']:.3f}")
    print(f"  Median: {stats['median']:.3f}")
    print(f"  Samples: {stats['n_samples']}")

    return stats


def save_calibration(
    body_factor: float,
    body_stats: dict,
    body_results: list[BodyCalibrationResult],
    meta_tool_overhead: int,
    meta_tool_measurements: list[int],
    output_path: Path,
) -> None:
    """Save calibration data to JSON file."""
    calibration_data = {
        "timestamp": datetime.now().isoformat(),
        "model": "Qwen3.5-9B-UD-Q4_K_XL.gguf",
        "base_url": "http://localhost:8001",
        "body_factor": body_factor,
        "meta_tool_overhead_tokens": meta_tool_overhead,
        "body_statistics": body_stats,
        "meta_tool_measurements": meta_tool_measurements,
        "measurements": [asdict(r) for r in body_results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(calibration_data, f, indent=2)

    print(f"\nCalibration data written to: {output_path}")


async def main() -> int:
    """Run calibration and save results."""
    print("Hestia Token Count Calibration (Two-Number Method)")
    print("=" * 55)
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

    if not await check_health():
        print("\nERROR: Cannot connect to llama-server at localhost:8001")
        print("Make sure the server is running before running calibration.")
        return 1

    print("Server is healthy. Running calibration...\n")

    # Run calibrations
    client = InferenceClient("http://localhost:8001", "Qwen3.5-9B-UD-Q4_K_XL.gguf")

    try:
        body_factor, body_results = await calibrate_body_factor(client)
        body_stats = print_body_results(body_results)

        meta_tool_overhead, meta_tool_measurements = await calibrate_meta_tool_overhead(client)

        print(f"\nMeta-Tool Overhead: {meta_tool_overhead} tokens")
        print(f"  (measured {len(meta_tool_measurements)} times, values: {meta_tool_measurements})")

    finally:
        await client.close()

    # Save to file
    output_path = Path("docs/calibration.json")
    save_calibration(
        body_factor=body_factor,
        body_stats=body_stats,
        body_results=body_results,
        meta_tool_overhead=meta_tool_overhead,
        meta_tool_measurements=meta_tool_measurements,
        output_path=output_path,
    )

    print(f"\nCalibration complete!")
    print(f"  body_factor: {body_factor:.3f}")
    print(f"  meta_tool_overhead_tokens: {meta_tool_overhead}")
    print(f"\nBudget formula:")
    print(f"  corrected = int(predicted_body / {body_factor:.3f}) + {meta_tool_overhead}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
