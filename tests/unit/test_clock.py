"""Tests for the centralized clock utility."""

from datetime import UTC

from hestia.core.clock import utcnow


def test_utcnow_returns_timezone_aware_datetime():
    """utcnow() must return a datetime with tzinfo=timezone.utc."""
    result = utcnow()
    assert result.tzinfo is UTC
