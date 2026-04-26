"""Environment-variable config mixin and coercion helpers."""

from __future__ import annotations

import dataclasses
import json
import os
import types
import warnings
from pathlib import Path
from typing import Any, ClassVar, Literal, Self, Union, get_args, get_origin, get_type_hints


def _is_optional(field_type: Any) -> bool:
    """Return True if *field_type* is ``X | None``."""
    origin = get_origin(field_type)
    if origin is not Union and origin is not types.UnionType:
        return False
    return type(None) in get_args(field_type)


def _coerce_env_value(raw: str, field_type: Any, field_name: str) -> Any:
    """Convert a raw env string to the Python type indicated by *field_type*.

    Raises ``ValueError`` with a clear message on parse failure.
    """
    origin = get_origin(field_type)
    args = get_args(field_type)

    # Optional[X]  (including X | None)
    if _is_optional(field_type):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            inner = non_none[0]
            if raw.strip() == "":
                return None
            return _coerce_env_value(raw, inner, field_name)
        # Complex union – fall back to string
        return raw

    # Literal[...]
    if origin is Literal:
        return raw

    # list[str]
    if origin is list:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON for {field_name}: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError(
                f"expected JSON list for {field_name}, got {type(parsed).__name__}"
            )
        if args and args[0] is str and not all(isinstance(x, str) for x in parsed):
            raise ValueError(f"expected JSON list of strings for {field_name}")
        return parsed

    # tuple[int, ...] or tuple[str, ...]
    if origin is tuple:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Fall back to comma-separated for non-JSON input (legacy env values)
            parsed = [x.strip() for x in raw.split(",") if x.strip()]
        if isinstance(parsed, int):
            # Bare integer like "123" for tuple[int, ...] — wrap it
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError(
                f"expected JSON list for {field_name}, got {type(parsed).__name__}"
            )
        if args and args[-1] is Ellipsis and len(args) == 2:
            inner_type = args[0]
            try:
                return tuple(inner_type(x) for x in parsed)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"expected JSON list of {inner_type.__name__} for {field_name}: {exc}"
                ) from exc
        # Fixed-length tuple – coerce each element if we can, else return tuple
        return tuple(parsed)

    # Basic scalar types
    if field_type is str:
        return raw
    if field_type is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"expected integer for {field_name}, got {raw!r}") from exc
    if field_type is float:
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"expected float for {field_name}, got {raw!r}") from exc
    if field_type is bool:
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"expected boolean for {field_name}, got {raw!r}")
    if field_type is Path:
        return Path(raw)

    # Unsupported – caller should skip
    raise TypeError(f"unsupported env type {field_type!r} for {field_name}")


class _ConfigFromEnv:
    """Mixin that adds ``from_env`` to dataclass-based config objects."""

    _ENV_PREFIX: ClassVar[str] = ""
    _ENV_KEY_OVERRIDES: ClassVar[dict[str, str]] = {}
    _LEGACY_ALIASES: ClassVar[dict[str, list[str]]] = {}

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Self:
        """Instantiate from environment variables.

        The canonical prefix is ``HESTIA_{_ENV_PREFIX}_*``.  When
        ``_ENV_PREFIX`` is empty it is derived from the class name
        (e.g. ``InferenceConfig`` → ``INFERENCE``).
        """
        env = environ if environ is not None else os.environ
        prefix = cls._ENV_PREFIX or cls.__name__.removesuffix("Config").upper()
        return cls(**cls.from_env_dict(prefix, env))

    @classmethod
    def from_env_dict(
        cls, prefix: str, environ: dict[str, str] | os._Environ[str]
    ) -> dict[str, Any]:
        """Build a kwargs dict for the dataclass constructor.

        Handles ``str``, ``int``, ``float``, ``bool``, ``Path``,
        ``list[str]``, ``tuple[int, ...]``, ``tuple[str, ...]`` and
        optional variants.
        """
        hints = get_type_hints(cls)
        result: dict[str, Any] = {}

        assert dataclasses.is_dataclass(cls)
        for f in dataclasses.fields(cls):
            if not f.init:
                continue

            field_type = hints.get(f.name, f.type)
            env_key = cls._ENV_KEY_OVERRIDES.get(
                f.name, f"HESTIA_{prefix}_{f.name.upper()}"
            )

            raw = environ.get(env_key)
            if raw is None:
                for legacy_key in cls._LEGACY_ALIASES.get(env_key, []):
                    raw = environ.get(legacy_key)
                    if raw is not None:
                        warnings.warn(
                            f"Legacy env key {legacy_key!r} is deprecated, "
                            f"use {env_key!r}",
                            DeprecationWarning,
                            stacklevel=4,
                        )
                        break

            if raw is None:
                continue  # use dataclass default

            # Empty string for non-str/non-Literal types means "use default"
            if raw.strip() == "":
                effective_type = field_type
                if _is_optional(field_type):
                    non_none = [a for a in get_args(field_type) if a is not type(None)]
                    if len(non_none) == 1:
                        effective_type = non_none[0]
                if effective_type is str or (
                    get_origin(effective_type) is Literal and "" in get_args(effective_type)
                ):
                    pass  # allow empty string
                else:
                    continue

            # Skip complex nested types (sub-configs, dicts, etc.)
            if dataclasses.is_dataclass(field_type) and isinstance(field_type, type):
                continue
            if get_origin(field_type) in (dict,):
                continue

            try:
                value = _coerce_env_value(raw, field_type, f.name)
            except ValueError as exc:
                raise ValueError(f"{env_key}: {exc}") from exc

            result[f.name] = value

        return result
