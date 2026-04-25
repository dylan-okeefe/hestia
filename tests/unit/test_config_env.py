"""Integration tests for _ConfigFromEnv and _coerce_env_value."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pytest

from hestia.config_env import _coerce_env_value, _ConfigFromEnv


@dataclass
class _NestedDummy:
    value: str = "nested_default"


@dataclass
class _DummyConfig(_ConfigFromEnv):
    """Minimal dataclass for testing coercion paths."""

    _ENV_PREFIX = "DUMMY"
    _ENV_KEY_OVERRIDES = {"custom_key": "MY_CUSTOM_KEY"}
    _LEGACY_ALIASES = {"HESTIA_DUMMY_LEGACY_FIELD": ["OLD_LEGACY_FIELD"]}

    name: str = "default"
    count: int = 0
    ratio: float = 1.0
    flag: bool = False
    tags: list[str] = field(default_factory=list)
    maybe: str | None = None
    path: Path = field(default_factory=lambda: Path("."))
    provider: Literal["a", "b"] = "a"
    custom_key: str = "default_custom"
    legacy_field: str = "default_legacy"
    str_tuple: tuple[str, ...] | None = None
    int_tuple: tuple[int, ...] | None = None
    dict_field: dict[str, Any] = field(default_factory=dict)
    nested: _NestedDummy = field(default_factory=_NestedDummy)
    union_field: str | int | None = None
    empty_literal: Literal["a", ""] = "a"


class TestCoerceEnvValue:
    """Direct tests for _coerce_env_value."""

    def test_bad_type_coercion_int(self):
        with pytest.raises(ValueError, match="expected integer"):
            _coerce_env_value("not_a_number", int, "count")

    def test_bad_type_coercion_float(self):
        with pytest.raises(ValueError, match="expected float"):
            _coerce_env_value("not_a_float", float, "ratio")

    def test_bad_type_coercion_bool(self):
        with pytest.raises(ValueError, match="expected boolean"):
            _coerce_env_value("maybe", bool, "flag")

    def test_bad_type_coercion_list_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _coerce_env_value("not-json", list[str], "tags")

    def test_bad_type_coercion_list_of_non_strings(self):
        with pytest.raises(ValueError, match="expected JSON list of strings"):
            _coerce_env_value("[1, 2, 3]", list[str], "tags")

    def test_tuple_str_json(self):
        assert _coerce_env_value('["a", "b"]', tuple[str, ...], "x") == ("a", "b")

    def test_tuple_str_comma_separated(self):
        assert _coerce_env_value("a, b", tuple[str, ...], "x") == ("a", "b")

    def test_tuple_int_json(self):
        assert _coerce_env_value("[1, 2]", tuple[int, ...], "x") == (1, 2)

    def test_tuple_int_comma_separated(self):
        assert _coerce_env_value("1, 2", tuple[int, ...], "x") == (1, 2)

    def test_missing_env_var_uses_default(self):
        cfg = _DummyConfig.from_env(environ={})
        assert cfg.name == "default"
        assert cfg.count == 0
        assert cfg.ratio == 1.0
        assert cfg.flag is False
        assert cfg.tags == []
        assert cfg.maybe is None

    def test_list_parsing_from_env_string(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_TAGS": '["a", "b", "c"]'})
        assert cfg.tags == ["a", "b", "c"]

    def test_list_parsing_empty_list(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_TAGS": "[]"})
        assert cfg.tags == []

    def test_bool_parsing_true_variants(self):
        for val in ("1", "true", "yes", "on", "TRUE", "Yes", "ON"):
            cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_FLAG": val})
            assert cfg.flag is True, val

    def test_bool_parsing_false_variants(self):
        for val in ("0", "false", "no", "off", "FALSE", "No", "OFF"):
            cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_FLAG": val})
            assert cfg.flag is False, val

    def test_optional_empty_string_becomes_none(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_MAYBE": ""})
        assert cfg.maybe is None

    def test_optional_non_empty_string_parses(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_MAYBE": "hello"})
        assert cfg.maybe == "hello"

    def test_path_parsing(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_PATH": "/tmp/data"})
        assert cfg.path == Path("/tmp/data")

    def test_int_parsing(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_COUNT": "42"})
        assert cfg.count == 42

    def test_float_parsing(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_RATIO": "3.14"})
        assert cfg.ratio == 3.14

    def test_literal_parsing(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_PROVIDER": "b"})
        assert cfg.provider == "b"

    def test_empty_string_for_non_str_uses_default(self):
        """Empty string for int/float/bool should fall back to default."""
        cfg = _DummyConfig.from_env(
            environ={
                "HESTIA_DUMMY_COUNT": "",
                "HESTIA_DUMMY_RATIO": "",
                "HESTIA_DUMMY_FLAG": "",
            }
        )
        assert cfg.count == 0
        assert cfg.ratio == 1.0
        assert cfg.flag is False

    def test_env_key_error_prefixes_field_name(self):
        with pytest.raises(ValueError, match="HESTIA_DUMMY_COUNT"):
            _DummyConfig.from_env(environ={"HESTIA_DUMMY_COUNT": "bad"})

    def test_env_key_override_reads_custom_key(self):
        cfg = _DummyConfig.from_env(environ={"MY_CUSTOM_KEY": "custom_value"})
        assert cfg.custom_key == "custom_value"

    def test_legacy_alias_fallback_with_deprecation_warning(self):
        with pytest.warns(DeprecationWarning, match="OLD_LEGACY_FIELD"):
            cfg = _DummyConfig.from_env(environ={"OLD_LEGACY_FIELD": "legacy_value"})
        assert cfg.legacy_field == "legacy_value"

    def test_tuple_str_parsing_json(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_STR_TUPLE": '["a", "b"]'})
        assert cfg.str_tuple == ("a", "b")

    def test_tuple_str_parsing_comma_separated(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_STR_TUPLE": "a, b, c"})
        assert cfg.str_tuple == ("a", "b", "c")

    def test_tuple_int_parsing_json(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_INT_TUPLE": "[1, 2, 3]"})
        assert cfg.int_tuple == (1, 2, 3)

    def test_tuple_int_parsing_comma_separated(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_INT_TUPLE": "1, 2, 3"})
        assert cfg.int_tuple == (1, 2, 3)

    def test_dict_field_skipped_uses_default(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_DICT_FIELD": '{"k": "v"}'})
        assert cfg.dict_field == {}

    def test_nested_dataclass_skipped_uses_default(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_NESTED": "ignored"})
        assert cfg.nested.value == "nested_default"

    def test_complex_union_fallback_returns_raw_string(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_UNION_FIELD": "hello"})
        assert cfg.union_field == "hello"

    def test_from_env_uses_real_os_environ_when_none(self, monkeypatch):
        monkeypatch.setattr(os, "environ", {"HESTIA_DUMMY_NAME": "from_os"})
        cfg = _DummyConfig.from_env()
        assert cfg.name == "from_os"

    def test_empty_string_literal_sets_empty_string(self):
        cfg = _DummyConfig.from_env(environ={"HESTIA_DUMMY_EMPTY_LITERAL": ""})
        assert cfg.empty_literal == ""
