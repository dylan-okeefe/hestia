"""Regression test: StyleProfileBuilder must not have dead get_profile_dict stub (§5 L28)."""

from __future__ import annotations

from hestia.style.builder import StyleProfileBuilder


def test_style_profile_builder_has_no_get_profile_dict() -> None:
    """The dead synchronous stub was removed; real implementation is on StyleStore."""
    assert not hasattr(StyleProfileBuilder, "get_profile_dict")
