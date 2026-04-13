"""Mock llama.cpp server for deterministic e2e tests.

This is a simple HTTP server that mimics the llama.cpp server API
but returns canned responses based on the request content.
"""

from __future__ import annotations

import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any


# Canned responses for common test patterns
CANNED_RESPONSES: list[tuple[re.Pattern, dict[str, Any]]] = [
    # Greeting pattern
    (
        re.compile(r"hello|hi there|hey", re.IGNORECASE),
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello! I'm Hestia, your personal assistant. How can I help you today?",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        },
    ),
    # Time query pattern - triggers tool use
    (
        re.compile(r"what time|current time|time is it", re.IGNORECASE),
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_001",
                                "type": "function",
                                "function": {
                                    "name": "current_time",
                                    "arguments": '{"timezone": "UTC"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 20, "total_tokens": 35},
        },
    ),
    # Memory save pattern
    (
        re.compile(r"remember.*favorite.*color.*blue", re.IGNORECASE),
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_002",
                                "type": "function",
                                "function": {
                                    "name": "save_memory",
                                    "arguments": '{"content": "User\'s favorite color is blue", "tags": ["preferences"]}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 25, "total_tokens": 45},
        },
    ),
    # Memory search pattern
    (
        re.compile(r"search.*favorite color|find.*favorite color", re.IGNORECASE),
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_003",
                                "type": "function",
                                "function": {
                                    "name": "search_memory",
                                    "arguments": '{"query": "favorite color"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 20, "total_tokens": 35},
        },
    ),
    # Write file pattern - triggers confirmation
    (
        re.compile(r"write.*file|create.*file|save.*file", re.IGNORECASE),
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_004",
                                "type": "function",
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"path": "/tmp/test.txt", "content": "Hello World"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40},
        },
    ),
    # Follow-up pattern (multi-turn)
    (
        re.compile(r"what did i just say|what was my previous", re.IGNORECASE),
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "You were asking about my favorite color earlier in our conversation.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65},
        },
    ),
]

# Default fallback response
DEFAULT_RESPONSE: dict[str, Any] = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "I understand. Let me know if you need anything else.",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
}


class MockLlamaHandler(BaseHTTPRequestHandler):
    """HTTP handler for mock llama.cpp server."""

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging."""
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self) -> None:
        """Handle GET requests (health check)."""
        if self.path == "/health":
            self._send_json({"status": "ok", "model": "mock-llama", "version": "e2e-test"})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        """Handle POST requests (chat completions)."""
        if self.path == "/v1/chat/completions":
            self._handle_chat_completions()
        else:
            self.send_error(404)

    def _handle_chat_completions(self) -> None:
        """Handle chat completion request with canned response."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        try:
            request = json.loads(body)
            messages = request.get("messages", [])

            # Get the last user message
            user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

            # Find matching canned response
            response = DEFAULT_RESPONSE
            for pattern, canned in CANNED_RESPONSES:
                if pattern.search(user_message):
                    response = canned
                    break

            self._send_json(response)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")


def run_server(host: str = "127.0.0.1", port: int = 9999) -> None:
    """Run the mock llama server."""
    server = HTTPServer((host, port), MockLlamaHandler)
    print(f"Mock llama server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down mock server...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
