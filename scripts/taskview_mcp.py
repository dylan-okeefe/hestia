#!/usr/bin/env python3
"""Minimal TaskView MCP client for the repair agent.

Wraps the ``taskview-mcp`` stdio server so the Telegram coding agent (and
humans) can create/update TaskView cards from bash without an MCP-capable
host. Configuration comes from the environment (set on hestia-tg-agent.service):

    TASKVIEW_URL   e.g. http://<taskview-host>:8888
    TASKVIEW_TOKEN API token (tvk_...)

Examples:
    python3 scripts/taskview_mcp.py create-task \
        --goal 1 --title "Voice replies on Matrix" \
        --note "Requested by Timo in the repair group: ..."
    python3 scripts/taskview_mcp.py list-goals
    python3 scripts/taskview_mcp.py call create_task '{"goalId": 1, "description": "x"}'

Exit code 0 on success; the tool's JSON result is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

_NPX = shutil.which("npx") or os.path.expanduser(
    "~/.nvm/versions/node/v24.18.0/bin/npx"
)
_PACKAGE = "taskview-mcp@1.45.0"
_PROTOCOL_VERSION = "2024-11-05"


class McpError(RuntimeError):
    """The MCP server returned an error or closed the connection."""


def _run(tool: str, arguments: dict, timeout: float = 60.0) -> dict:
    if not os.environ.get("TASKVIEW_TOKEN"):
        raise McpError("TASKVIEW_TOKEN is not set in the environment")
    proc = subprocess.Popen(
        [_NPX, "-y", _PACKAGE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stdin is not None and proc.stdout is not None

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv() -> dict:
        line = proc.stdout.readline()
        if not line.strip():
            raise McpError("taskview-mcp closed the connection")
        return json.loads(line)

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "taskview-cli", "version": "1.0"},
                },
            }
        )
        recv()  # initialize result
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
        while True:
            msg = recv()
            if msg.get("id") == 2:
                if "error" in msg:
                    raise McpError(json.dumps(msg["error"]))
                result = msg.get("result", {})
                if result.get("isError"):
                    raise McpError(json.dumps(result.get("content")))
                return result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _content_text(result: dict) -> str:
    parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-task", help="Create a TaskView card")
    p_create.add_argument("--goal", type=int, default=1, help="Goal (project) ID")
    p_create.add_argument("--title", required=True, help="Card title/description")
    p_create.add_argument("--note", default=None, help="Card note (markdown)")
    p_create.add_argument(
        "--priority", type=int, choices=[1, 2, 3], default=None, help="1=low 2=medium 3=high"
    )

    sub.add_parser("list-goals", help="List accessible projects")

    p_call = sub.add_parser("call", help="Call any taskview-mcp tool with raw JSON args")
    p_call.add_argument("tool", help="Tool name, e.g. create_task")
    p_call.add_argument("arguments", help="JSON object of tool arguments")

    args = parser.parse_args()

    try:
        if args.cmd == "create-task":
            arguments: dict = {"goalId": args.goal, "description": args.title}
            if args.note:
                arguments["note"] = args.note
            if args.priority:
                arguments["priorityId"] = args.priority
            result = _run("create_task", arguments)
        elif args.cmd == "list-goals":
            result = _run("list_goals", {})
        else:
            result = _run(args.tool, json.loads(args.arguments))
    except (McpError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    text = _content_text(result)
    print(text if text else json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
