"""Unit tests for scheduler-related types."""

from datetime import datetime, timezone

import pytest

from hestia.core.types import ScheduledTask


class TestScheduledTask:
    """Tests for ScheduledTask validation."""

    def _make_task(self, **kwargs):
        """Create a ScheduledTask with sensible defaults."""
        defaults = {
            "id": "task-1",
            "session_id": "sess-1",
            "prompt": "test prompt",
            "description": None,
            "cron_expression": None,
            "fire_at": None,
            "enabled": True,
            "created_at": datetime.now(timezone.utc),
            "last_run_at": None,
            "next_run_at": None,
            "last_error": None,
            "notify": False,
        }
        defaults.update(kwargs)
        return ScheduledTask(**defaults)

    def test_cron_only_is_valid(self):
        """Exactly one of cron_expression is valid."""
        task = self._make_task(cron_expression="0 9 * * *")
        assert task.cron_expression == "0 9 * * *"
        assert task.fire_at is None

    def test_fire_at_only_is_valid(self):
        """Exactly one of fire_at is valid."""
        task = self._make_task(fire_at=datetime.now(timezone.utc))
        assert task.cron_expression is None
        assert task.fire_at is not None

    def test_both_set_raises(self):
        """Both cron_expression and fire_at raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one of cron_expression or fire_at must be set"):
            self._make_task(cron_expression="0 9 * * *", fire_at=datetime.now(timezone.utc))

    def test_neither_set_raises(self):
        """Neither cron_expression nor fire_at raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one of cron_expression or fire_at must be set"):
            self._make_task()

    def test_empty_string_cron_treated_as_unset(self):
        """Empty string cron_expression is treated as unset."""
        with pytest.raises(ValueError, match="Exactly one of cron_expression or fire_at must be set"):
            self._make_task(cron_expression="")
