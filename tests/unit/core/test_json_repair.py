"""Unit tests for repair_json utility."""

from hestia.core.json_repair import repair_json


class TestRepairJson:
    """Tests for the repair_json function."""

    def test_valid_json_unchanged(self) -> None:
        """Valid JSON is returned unchanged."""
        text = '{"name": "foo", "arguments": {"x": 1}}'
        assert repair_json(text) == text

    def test_trailing_comma_fixed(self) -> None:
        """Trailing commas before } or ] are removed."""
        assert repair_json('{"a": 1,}') == '{"a": 1}'
        assert repair_json('[1, 2,]') == '[1, 2]'
        assert repair_json('{"a": [1, 2,],}') == '{"a": [1, 2]}'

    def test_single_quotes_fixed(self) -> None:
        """Single-quoted strings are converted to double quotes."""
        result = repair_json("{'name': 'foo', 'arguments': {}}")
        assert result == '{"name": "foo", "arguments": {}}'

    def test_unquoted_keys_fixed(self) -> None:
        """Unquoted object keys are wrapped in double quotes."""
        result = repair_json('{name: "foo", arguments: {}}')
        assert result == '{"name": "foo", "arguments": {}}'

    def test_missing_closing_brace_fixed(self) -> None:
        """Missing closing braces are appended."""
        result = repair_json('{"name": "foo", "arguments": {"x": 1}')
        assert result == '{"name": "foo", "arguments": {"x": 1}}'

    def test_missing_closing_bracket_fixed(self) -> None:
        """Missing closing brackets are appended."""
        result = repair_json('[1, 2')
        assert result == '[1, 2]'

    def test_fenced_block_extracted(self) -> None:
        """JSON inside markdown fences is extracted and repaired."""
        text = '```json\n{"a": 1,}\n```'
        assert repair_json(text) == '{"a": 1}'

    def test_fenced_block_without_language(self) -> None:
        """JSON inside plain ``` fences is extracted."""
        text = '```\n{"b": 2,}\n```'
        assert repair_json(text) == '{"b": 2}'

    def test_literal_newlines_escaped(self) -> None:
        """Literal newlines inside strings are escaped."""
        text = '{"message": "line one\nline two"}'
        result = repair_json(text)
        assert result == '{"message": "line one\\nline two"}'
        import json

        assert json.loads(result) == {"message": "line one\nline two"}

    def test_literal_tabs_escaped(self) -> None:
        """Literal tabs inside strings are escaped."""
        text = '{"message": "col one\tcol two"}'
        result = repair_json(text)
        assert result == '{"message": "col one\\tcol two"}'
        import json

        assert json.loads(result) == {"message": "col one\tcol two"}

    def test_extract_first_object_from_prefix(self) -> None:
        """Only the first JSON object is extracted from surrounding text."""
        text = 'Here is the result: {"name": "foo", "arguments": {}} thanks!'
        assert repair_json(text) == '{"name": "foo", "arguments": {}}'

    def test_unrecoverable_garbage_returns_none(self) -> None:
        """Completely unparseable input returns None."""
        assert repair_json("") is None
        assert repair_json("   ") is None
        assert repair_json("no json here") is None
        assert repair_json("{broken: unquoted value with no key}") is None

    def test_combined_repairs(self) -> None:
        """Multiple issues are repaired in one pass."""
        text = "{'name': 'foo', arguments: {'x': 1,},"
        result = repair_json(text)
        assert result == '{"name": "foo", "arguments": {"x": 1}}'

    def test_nested_object_with_trailing_comma(self) -> None:
        """Trailing commas in nested objects are fixed."""
        text = '{"outer": {"inner": 1,},}'
        assert repair_json(text) == '{"outer": {"inner": 1}}'

    def test_array_of_objects(self) -> None:
        """Arrays containing objects are handled."""
        text = '[{"a": 1,}, {"b": 2,},]'
        assert repair_json(text) == '[{"a": 1}, {"b": 2}]'

    def test_preserves_escaped_quotes(self) -> None:
        """Already-escaped quotes are preserved."""
        text = '{"msg": "say \\"hello\\""}'
        assert repair_json(text) == '{"msg": "say \\"hello\\""}'
