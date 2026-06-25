"""Tests for browser_get_json helpers."""

from __future__ import annotations

import pytest

from hestia.tools.builtin.browser_get_json import (
    _extract_variable,
    _get_path,
    _parse_variable_name,
)


class TestParseVariableName:
    """Tests for _parse_variable_name."""

    def test_simple_root(self) -> None:
        assert _parse_variable_name("_initialData") == ("_initialData", None)

    def test_window_prefix(self) -> None:
        assert _parse_variable_name("window._initialData") == ("_initialData", None)

    def test_bracket_access(self) -> None:
        root, path = _parse_variable_name(
            'window.mosaic.providerData["mosaic-provider-jobcards"]'
        )
        assert root == "mosaic"
        assert path == ["providerData", "mosaic-provider-jobcards"]

    def test_mixed_dot_and_bracket(self) -> None:
        root, path = _parse_variable_name('foo.bar["baz"].qux')
        assert root == "foo"
        assert path == ["bar", "baz", "qux"]

    def test_invalid_empty(self) -> None:
        with pytest.raises(ValueError):
            _parse_variable_name("")


class TestExtractVariable:
    """Tests for _extract_variable."""

    def test_extracts_simple_assignment(self) -> None:
        html = "<script>var _initialData = {\"foo\": 1};</script>"
        data = _extract_variable(html, "_initialData")
        assert data == {"foo": 1}

    def test_extracts_window_assignment(self) -> None:
        html = "<script>window._initialData = {\"foo\": 1};</script>"
        data = _extract_variable(html, "_initialData")
        assert data == {"foo": 1}

    def test_extracts_bracket_assignment(self) -> None:
        html = '<script>window.mosaic.providerData["mosaic-provider-jobcards"] = {"results": []};</script>'
        data = _extract_variable(html, "mosaic")
        assert data == {"providerData": {"mosaic-provider-jobcards": {"results": []}}}

    def test_returns_none_when_missing(self) -> None:
        html = "<script>var other = {};</script>"
        assert _extract_variable(html, "_initialData") is None

    def test_ignores_invalid_json(self) -> None:
        html = "<script>var _initialData = {not valid json};</script>"
        assert _extract_variable(html, "_initialData") is None


class TestGetPath:
    """Tests for _get_path."""

    def test_empty_path_returns_data(self) -> None:
        assert _get_path({"a": 1}, "") == {"a": 1}

    def test_navigates_dict(self) -> None:
        data = {"meta": {"results": [{"title": "Engineer"}]}}
        assert _get_path(data, "meta.results.0.title") == "Engineer"

    def test_missing_key_raises(self) -> None:
        with pytest.raises(KeyError):
            _get_path({"a": 1}, "b")

    def test_index_out_of_range_raises(self) -> None:
        with pytest.raises(IndexError):
            _get_path([1, 2], "5")

    def test_non_integer_index_raises(self) -> None:
        with pytest.raises(KeyError):
            _get_path([1, 2], "foo")
