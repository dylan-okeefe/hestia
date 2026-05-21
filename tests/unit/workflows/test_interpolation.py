"""Tests for the workflow variable interpolation engine."""

from __future__ import annotations

from hestia.workflows.interpolation import interpolate


class TestInterpolate:
    def test_simple_key_replacement(self) -> None:
        assert interpolate("Hello {{name}}!", {"name": "Hestia"}) == "Hello Hestia!"

    def test_nested_field_replacement(self) -> None:
        assert (
            interpolate("Value: {{node_id.field}}", {"node_id": {"field": 42}})
            == "Value: 42"
        )

    def test_missing_key_returns_empty_string(self) -> None:
        assert interpolate("Hello {{missing}}!", {}) == "Hello !"

    def test_non_dict_intermediate_returns_empty_string(self) -> None:
        assert interpolate("Bad: {{a.b}}", {"a": "string"}) == "Bad: "

    def test_none_value_returns_empty_string(self) -> None:
        assert interpolate("Val: {{key}}", {"key": None}) == "Val: "

    def test_multiple_placeholders(self) -> None:
        assert (
            interpolate("{{greet}} {{name}}!", {"greet": "Hi", "name": "Alice"})
            == "Hi Alice!"
        )

    def test_whitespace_inside_braces(self) -> None:
        assert interpolate("{{  key  }}", {"key": "x"}) == "x"
