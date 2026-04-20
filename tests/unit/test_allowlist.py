"""Tests for platform allow-list matching and validation (L45c)."""

from __future__ import annotations

import pytest

from hestia.platforms.allowlist import (
    match_allowlist,
    validate_matrix_room_id,
    validate_telegram_user_id,
    validate_telegram_username,
)


class TestMatchAllowlist:
    def test_empty_list_denies_all(self):
        """Empty pattern list is secure default: deny all."""
        assert match_allowlist([], "anything") is False
        assert match_allowlist([], "") is False

    def test_exact_match(self):
        """Exact string match works."""
        assert match_allowlist(["alice", "bob"], "alice") is True
        assert match_allowlist(["alice", "bob"], "bob") is True
        assert match_allowlist(["alice", "bob"], "charlie") is False

    def test_wildcard_star(self):
        """* matches any sequence of characters."""
        assert match_allowlist(["admin_*"], "admin_alice") is True
        assert match_allowlist(["admin_*"], "admin_bob") is True
        assert match_allowlist(["admin_*"], "super_admin_alice") is False

    def test_wildcard_prefix(self):
        """* at the start matches suffixes."""
        assert match_allowlist(["*_admin"], "alice_admin") is True
        assert match_allowlist(["*_admin"], "bob_admin") is True
        assert match_allowlist(["*_admin"], "admin_alice") is False

    def test_wildcard_question(self):
        """? matches exactly one character."""
        assert match_allowlist(["user_?"], "user_a") is True
        assert match_allowlist(["user_?"], "user_z") is True
        assert match_allowlist(["user_?"], "user_ab") is False

    def test_case_sensitive_default(self):
        """Default matching is case-sensitive."""
        assert match_allowlist(["Alice"], "alice") is False
        assert match_allowlist(["Alice"], "Alice") is True

    def test_case_insensitive(self):
        """Case-insensitive matching option works."""
        assert match_allowlist(["Alice"], "alice", case_sensitive=False) is True
        assert match_allowlist(["ALICE"], "alice", case_sensitive=False) is True

    def test_multiple_patterns(self):
        """Value matching any pattern in the list is allowed."""
        patterns = ["admin_*", "guest_*", "superuser"]
        assert match_allowlist(patterns, "admin_alice") is True
        assert match_allowlist(patterns, "guest_bob") is True
        assert match_allowlist(patterns, "superuser") is True
        assert match_allowlist(patterns, "hacker_eve") is False


class TestValidateTelegramUserId:
    def test_numeric_id(self):
        assert validate_telegram_user_id("123456789") is True

    def test_non_numeric(self):
        assert validate_telegram_user_id("alice") is False
        assert validate_telegram_user_id("123abc") is False

    def test_empty(self):
        assert validate_telegram_user_id("") is False


class TestValidateTelegramUsername:
    def test_valid_username(self):
        assert validate_telegram_username("alice") is True
        assert validate_telegram_username("alice_smith") is True
        assert validate_telegram_username("a12345") is True

    def test_valid_with_at(self):
        assert validate_telegram_username("@alice") is True

    def test_too_short(self):
        assert validate_telegram_username("abcd") is False

    def test_too_long(self):
        assert validate_telegram_username("a" * 33) is False

    def test_invalid_chars(self):
        assert validate_telegram_username("alice-smith") is False
        assert validate_telegram_username("alice.smith") is False

    def test_empty(self):
        assert validate_telegram_username("") is False
        assert validate_telegram_username("@") is False


class TestValidateMatrixRoomId:
    def test_valid_room_id(self):
        assert validate_matrix_room_id("!abc123:matrix.org") is True

    def test_valid_room_alias(self):
        assert validate_matrix_room_id("#family:matrix.org") is True

    def test_missing_colon(self):
        assert validate_matrix_room_id("!abc123") is False
        assert validate_matrix_room_id("#family") is False

    def test_missing_prefix(self):
        assert validate_matrix_room_id("family:matrix.org") is False

    def test_empty(self):
        assert validate_matrix_room_id("") is False


class TestTelegramAdapterAllowlist:
    @pytest.mark.asyncio
    async def test_empty_allowed_users_denies_all(self):
        """Empty allowed_users list denies every user."""
        from hestia.config import TelegramConfig
        from hestia.platforms.telegram_adapter import TelegramAdapter

        config = TelegramConfig(bot_token="dummy", allowed_users=[])
        adapter = TelegramAdapter(config)
        assert adapter._is_allowed(123456, "alice") is False
        assert adapter._is_allowed(789012, None) is False

    @pytest.mark.asyncio
    async def test_exact_user_id_match(self):
        from hestia.config import TelegramConfig
        from hestia.platforms.telegram_adapter import TelegramAdapter

        config = TelegramConfig(bot_token="dummy", allowed_users=["123456"])
        adapter = TelegramAdapter(config)
        assert adapter._is_allowed(123456, "alice") is True
        assert adapter._is_allowed(999999, "alice") is False

    @pytest.mark.asyncio
    async def test_exact_username_match(self):
        from hestia.config import TelegramConfig
        from hestia.platforms.telegram_adapter import TelegramAdapter

        config = TelegramConfig(bot_token="dummy", allowed_users=["alice"])
        adapter = TelegramAdapter(config)
        assert adapter._is_allowed(123456, "alice") is True
        assert adapter._is_allowed(123456, "Alice") is True  # case-insensitive
        assert adapter._is_allowed(123456, "bob") is False

    @pytest.mark.asyncio
    async def test_wildcard_username_match(self):
        from hestia.config import TelegramConfig
        from hestia.platforms.telegram_adapter import TelegramAdapter

        config = TelegramConfig(bot_token="dummy", allowed_users=["family_*"])
        adapter = TelegramAdapter(config)
        assert adapter._is_allowed(1, "family_alice") is True
        assert adapter._is_allowed(2, "family_bob") is True
        assert adapter._is_allowed(3, "work_alice") is False


class TestMatrixAdapterAllowlist:
    @pytest.mark.asyncio
    async def test_empty_allowed_rooms_denies_all(self):
        """Empty allowed_rooms list denies every room."""
        from hestia.config import MatrixConfig
        from hestia.platforms.matrix_adapter import MatrixAdapter

        config = MatrixConfig(access_token="dummy", user_id="@bot:example.com", allowed_rooms=[])
        adapter = MatrixAdapter(config)
        assert adapter._is_allowed("!abc:example.com") is False

    @pytest.mark.asyncio
    async def test_exact_room_match(self):
        from hestia.config import MatrixConfig
        from hestia.platforms.matrix_adapter import MatrixAdapter

        config = MatrixConfig(
            access_token="dummy",
            user_id="@bot:example.com",
            allowed_rooms=["!abc:example.com"],
        )
        adapter = MatrixAdapter(config)
        assert adapter._is_allowed("!abc:example.com") is True
        assert adapter._is_allowed("!xyz:example.com") is False

    @pytest.mark.asyncio
    async def test_wildcard_room_match(self):
        from hestia.config import MatrixConfig
        from hestia.platforms.matrix_adapter import MatrixAdapter

        config = MatrixConfig(
            access_token="dummy",
            user_id="@bot:example.com",
            allowed_rooms=["#ops-*:example.com"],
        )
        adapter = MatrixAdapter(config)
        assert adapter._is_allowed("#ops-deploy:example.com") is True
        assert adapter._is_allowed("#ops-alerts:example.com") is True
        assert adapter._is_allowed("#general:example.com") is False
