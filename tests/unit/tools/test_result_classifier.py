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
        # Markerless content containing failure-like words must not misfire.
        ("The error rate is zero", ToolResultCategory.SUCCESS),
        ("Page 404 not available in this catalog", ToolResultCategory.SUCCESS),
        ("Please login to apply for this job", ToolResultCategory.SUCCESS),
        ("Request timed out waiting for user input", ToolResultCategory.SUCCESS),
        ("ERROR: this is a documented edge case", ToolResultCategory.SUCCESS),
    ],
)
def test_classify_success(content: str, expected: ToolResultCategory) -> None:
    assert classify_tool_result(content) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("[CATEGORY: timeout] request timed out", ToolResultCategory.TIMEOUT),
        ("[CATEGORY: TIMEOUT]", ToolResultCategory.TIMEOUT),
        ("[category: timeout]", ToolResultCategory.TIMEOUT),
        ("[CATEGORY: not_found] 404", ToolResultCategory.NOT_FOUND),
        ("[CATEGORY: blocked] login required", ToolResultCategory.BLOCKED),
        ("[CATEGORY: transient_other] disk full", ToolResultCategory.TRANSIENT_OTHER),
    ],
)
def test_classify_trusts_category_marker(
    content: str, expected: ToolResultCategory
) -> None:
    assert classify_tool_result(content) == expected


def test_unknown_marker_defaults_to_success() -> None:
    assert classify_tool_result("[CATEGORY: unknown]") == ToolResultCategory.SUCCESS
