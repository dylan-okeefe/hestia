"""Tests for the regression fixture scrubber."""

import tempfile
from pathlib import Path

from hestia.diagnostics.scrub import scrub_fixture_file, scrub_text


class TestScrubText:
    def test_replaces_linux_home_paths(self):
        assert scrub_text("/home/someuser/Documents/file.txt") == "/home/<user>/Documents/file.txt"

    def test_replaces_windows_home_paths(self):
        assert scrub_text(r"C:\Users\dylan\Documents\file.txt") == r"C:\Users\<user>\Documents\file.txt"

    def test_replaces_emails(self):
        assert scrub_text("Contact alice@example.com please") == "Contact <email> please"

    def test_replaces_ips(self):
        assert scrub_text("Server at 192.168.1.42") == "Server at <ip>"

    def test_replaces_telegram_tokens(self):
        # Build the token at runtime so a static secret scanner never sees a
        # realistic-looking literal in the source.
        token = "123456789:" + "A" * 35
        assert scrub_text(f"bot token: {token}") == "bot token: <telegram-token>"

    def test_replaces_matrix_tokens(self):
        # Build the token at runtime so a static secret scanner never sees a
        # realistic-looking literal in the source.
        token = "syt_" + "T" * 24
        assert (
            scrub_text(f"Authorization: Bearer {token}")
            == "Authorization: Bearer <matrix-token>"
        )

    def test_replaces_cookie_header(self):
        assert (
            scrub_text("Cookie: sessionid=secret123; csrftoken=abc")
            == "Cookie: <redacted>"
        )

    def test_replaces_set_cookie_header(self):
        assert (
            scrub_text("Set-Cookie: session=supersecret; Path=/; HttpOnly")
            == "Set-Cookie: <redacted>"
        )

    def test_replaces_inline_session_cookie_values(self):
        assert (
            scrub_text("sessionid=secret123; csrftoken=abc")
            == "sessionid=<redacted>; csrftoken=<redacted>"
        )

    def test_replaces_linkedin_auth_cookies(self):
        # Inline form (not a full Cookie header) should redact each named value.
        assert (
            scrub_text("li_at=AQEDATg0MDI2MzUz0AAAAAABG1frKgE; JSESSIONID=node0xyz123")
            == "li_at=<redacted>; JSESSIONID=<redacted>"
        )

    def test_replaces_indeed_auth_cookies(self):
        assert (
            scrub_text("indeed_api_token=abc123def456; indeed_application_session_id=xyz789")
            == "indeed_api_token=<redacted>; indeed_application_session_id=<redacted>"
        )

    def test_high_entropy_catch_all_redacts_long_tokens(self):
        token = "Ab3dEfGh1JkLmNoPqRsTuVwXyZ012345"
        assert scrub_text(f"x-custom-auth={token}") == "x-custom-auth=<redacted>"

    def test_high_entropy_catch_all_ignores_long_words(self):
        # Long lowercase word with no digits should stay intact.
        assert (
            scrub_text("someconfigurationvaluewithoutdigits")
            == "someconfigurationvaluewithoutdigits"
        )

    def test_leaves_artifact_handles_intact(self):
        assert scrub_text("art_6c65504923") == "art_6c65504923"

    def test_leaves_urls_intact(self):
        assert (
            scrub_text("https://builtinboston.com/jobs?q=software")
            == "https://builtinboston.com/jobs?q=software"
        )


class TestScrubFixtureFile:
    def test_scrubs_and_returns_true_when_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.xml"
            path.write_text("/home/someuser/.hestia/artifacts/art_1234", encoding="utf-8")
            changed = scrub_fixture_file(path)
            assert changed is True
            assert path.read_text(encoding="utf-8") == "/home/<user>/.hestia/artifacts/art_1234"

    def test_returns_false_when_no_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.xml"
            path.write_text("no sensitive data here", encoding="utf-8")
            changed = scrub_fixture_file(path)
            assert changed is False

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.xml"
            original = "/home/someuser/.hestia/artifacts/art_1234"
            path.write_text(original, encoding="utf-8")
            changed = scrub_fixture_file(path, dry_run=True)
            assert changed is True
            assert path.read_text(encoding="utf-8") == original
