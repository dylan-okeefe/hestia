"""Regression tests for HTML sanitization in EmailAdapter (§1 L28)."""

from __future__ import annotations

from hestia.email.adapter import EmailAdapter, EmailConfig


class TestSanitizeHtml:
    """Tests for HTML stripping using nh3."""

    def test_sanitize_strips_script_tag(self) -> None:
        adapter = EmailAdapter(EmailConfig(sanitize_html=True))
        raw = "<p>hi</p><script>alert(1)</script>"
        result = adapter._sanitize_html(raw)
        assert "<script>" not in result
        assert "script" not in result.lower()
        assert "hi" in result

    def test_sanitize_disabled_passthrough(self) -> None:
        adapter = EmailAdapter(EmailConfig(sanitize_html=False))
        raw = "<p>Keep me</p>"
        result = adapter._sanitize_html(raw)
        assert result == raw

    def test_sanitize_handles_empty_string(self) -> None:
        adapter = EmailAdapter(EmailConfig(sanitize_html=True))
        result = adapter._sanitize_html("")
        assert result == ""
