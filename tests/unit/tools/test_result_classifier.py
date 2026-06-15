"""Tests for tool result classification."""

import pytest

from hestia.tools.result_classifier import ToolResultCategory, classify_tool_result


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("ok", ToolResultCategory.SUCCESS),
        ("Page loaded successfully", ToolResultCategory.SUCCESS),
        ("Here are the results", ToolResultCategory.SUCCESS),
        ("", ToolResultCategory.SUCCESS),
    ],
)
def test_classify_success(content: str, expected: ToolResultCategory) -> None:
    assert classify_tool_result(content) == expected


@pytest.mark.parametrize(
    "content",
    [
        "Timeout after 30s",
        "Request timed out",
        "operation timeout exceeded",
        "TIMED OUT",
    ],
)
def test_classify_timeout(content: str) -> None:
    assert classify_tool_result(content) == ToolResultCategory.TIMEOUT


@pytest.mark.parametrize(
    "content",
    [
        "404 not found",
        "Page doesn't exist",
        "The page is gone",
        "url returns 404",
        "Not Found",
    ],
)
def test_classify_not_found(content: str) -> None:
    assert classify_tool_result(content) == ToolResultCategory.NOT_FOUND


@pytest.mark.parametrize(
    "content",
    [
        "403 forbidden",
        "blocked by bot protection",
        "Cloudflare challenge",
        "captcha required",
        "Humans only",
        "please login",
        "sign in to continue",
        "unauthorized access",
        "Access Denied",
        "[BLOCKED - LOGIN_REQUIRED] re-authenticate",
        "[CHALLENGE] verify your identity",
        "verify your identity to continue",
        "security checkpoint reached",
        "welcome back, please sign in",
    ],
)
def test_classify_blocked(content: str) -> None:
    assert classify_tool_result(content) == ToolResultCategory.BLOCKED


@pytest.mark.parametrize(
    "content",
    [
        "An error occurred",
        "Tool failed",
        "partial failure",
        "ERROR: could not parse",
    ],
)
def test_classify_transient_other(content: str) -> None:
    assert classify_tool_result(content) == ToolResultCategory.TRANSIENT_OTHER


def test_blocked_takes_precedence_over_transient() -> None:
    """A message containing both blocked and transient markers is BLOCKED."""
    content = "Error: blocked by Cloudflare captcha"
    assert classify_tool_result(content) == ToolResultCategory.BLOCKED


def test_not_found_takes_precedence_over_transient() -> None:
    """A message containing both not-found and transient markers is NOT_FOUND."""
    content = "Error: 404 not found"
    assert classify_tool_result(content) == ToolResultCategory.NOT_FOUND


def test_timeout_takes_precedence_over_error() -> None:
    """A message containing both timeout and error markers is TIMEOUT."""
    content = "Error: request timed out"
    assert classify_tool_result(content) == ToolResultCategory.TIMEOUT
