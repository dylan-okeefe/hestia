"""Unit tests for EmailConfig password_env resolution."""

from __future__ import annotations

import pytest

from hestia.config import EmailConfig, EmailConfigError


class TestEmailConfigPasswordEnv:
    """Tests for EmailConfig.password_env resolution."""

    def test_password_env_resolves_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """password_env set and env var present => resolved value."""
        monkeypatch.setenv("EMAIL_TEST_PW", "secret_from_env")
        cfg = EmailConfig(password_env="EMAIL_TEST_PW")
        assert cfg.resolved_password == "secret_from_env"

    def test_password_env_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """password_env set but env var unset => EmailConfigError."""
        monkeypatch.delenv("MISSING_EMAIL_PW", raising=False)
        cfg = EmailConfig(password_env="MISSING_EMAIL_PW")
        with pytest.raises(EmailConfigError, match="environment variable is not defined"):
            _ = cfg.resolved_password

    def test_plaintext_password_still_works(self) -> None:
        """password without password_env => plaintext returned."""
        cfg = EmailConfig(password="plaintext_secret")
        assert cfg.resolved_password == "plaintext_secret"

    def test_env_takes_precedence_over_plaintext(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both password and password_env set => env wins."""
        monkeypatch.setenv("EMAIL_TEST_PW", "env_wins")
        cfg = EmailConfig(password="plaintext_loses", password_env="EMAIL_TEST_PW")
        assert cfg.resolved_password == "env_wins"
