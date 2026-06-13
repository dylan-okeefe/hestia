"""Tests that SECURITY.md contains required policy information."""

from __future__ import annotations

from pathlib import Path

import pytest

SECURITY_PATH = Path("SECURITY.md")
CONTACT_EMAIL = "dylanokeefedev@gmail.com"


def test_security_has_contact_email() -> None:
    """SECURITY.md must list a contact email for vulnerability reports."""
    text = SECURITY_PATH.read_text()
    assert CONTACT_EMAIL in text, (
        f"SECURITY.md must contain the maintainer contact email {CONTACT_EMAIL}"
    )


def test_security_has_supported_versions_section() -> None:
    """SECURITY.md must contain a supported-versions table or section."""
    text = SECURITY_PATH.read_text().lower()
    assert "supported versions" in text, (
        "SECURITY.md must contain a 'Supported versions' section"
    )
    assert "|" in text, "SECURITY.md supported-versions section should include a table"
