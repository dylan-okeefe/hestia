"""Tests that SECURITY.md contains required policy information."""

from __future__ import annotations

from pathlib import Path

SECURITY_PATH = Path("SECURITY.md")
RETIRED_PLACEHOLDER = "security@example.com"


def test_security_has_private_reporting_channel() -> None:
    """SECURITY.md must direct reporters at GitHub private vulnerability
    reporting - never a public issue, never an email placeholder."""
    text = SECURITY_PATH.read_text()
    assert (
        "Report a vulnerability" in text or "security/advisories/new" in text
    ), "SECURITY.md must point at GitHub private vulnerability reporting"
    assert RETIRED_PLACEHOLDER not in text, (
        "the security@example.com placeholder must not come back"
    )


def test_security_has_supported_versions_section() -> None:
    """SECURITY.md must state which versions receive fixes."""
    text = SECURITY_PATH.read_text().lower()
    assert "supported versions" in text, (
        "SECURITY.md must contain a 'Supported versions' section"
    )
