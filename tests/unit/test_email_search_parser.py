"""Regression tests for IMAP search query parser (§4 L28)."""

from __future__ import annotations

import pytest

from hestia.email.adapter import EmailAdapter, EmailAdapterError, EmailConfig


class TestSearchQueryParser:
    """Tests for _parse_search_query hardened against injection and bad dates."""

    def test_basic_from(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        result = adapter._parse_search_query("FROM:alice@example.com")
        assert result == '(FROM "alice@example.com")'

    def test_basic_subject(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        result = adapter._parse_search_query("SUBJECT:hello")
        assert result == '(SUBJECT "hello")'

    def test_basic_since(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        result = adapter._parse_search_query("SINCE:2026-04-18")
        assert result == '(SINCE "18-Apr-2026")'

    def test_quote_escaping(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        result = adapter._parse_search_query('FROM:alice"bob')
        assert result == '(FROM "alice\\"bob")'

    def test_imap_injection_attempt(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        result = adapter._parse_search_query('FROM:alice" OR ALL HEADER X ')
        # The quote is escaped inside the FROM clause; remaining tokens become
        # literal SUBJECT searches rather than IMAP commands.
        assert 'FROM "alice\\""' in result
        assert "SUBJECT \"OR\"" in result
        assert "SUBJECT \"ALL\"" in result
        assert "SUBJECT \"HEADER\"" in result
        assert "SUBJECT \"X\"" in result

    def test_malformed_since_raises(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        with pytest.raises(EmailAdapterError) as exc_info:
            adapter._parse_search_query("SINCE:2026-99-99")
        assert "Invalid SINCE date" in str(exc_info.value)
        assert "2026-99-99" in str(exc_info.value)

    def test_default_subject_search(self) -> None:
        adapter = EmailAdapter(EmailConfig())
        result = adapter._parse_search_query("hello world")
        assert result == '(SUBJECT "hello" SUBJECT "world")'
