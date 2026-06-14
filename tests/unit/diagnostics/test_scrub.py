"""Tests for the regression fixture scrubber."""

import tempfile
from pathlib import Path

import pytest

from hestia.diagnostics.scrub import scrub_fixture_file, scrub_text


class TestScrubText:
    def test_replaces_linux_home_paths(self):
        assert scrub_text("/home/dylan/Documents/file.txt") == "/home/<user>/Documents/file.txt"

    def test_replaces_windows_home_paths(self):
        assert scrub_text(r"C:\Users\dylan\Documents\file.txt") == r"C:\Users\<user>\Documents\file.txt"

    def test_replaces_emails(self):
        assert scrub_text("Contact alice@example.com please") == "Contact <email> please"

    def test_replaces_ips(self):
        assert scrub_text("Server at 192.168.1.42") == "Server at <ip>"

    def test_replaces_telegram_tokens(self):
        assert (
            scrub_text("bot token: 123456789:ABCDefghijklmnopqrstuvwxyz1234")
            == "bot token: <telegram-token>"
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
            path.write_text("/home/dylan/.hestia/artifacts/art_1234", encoding="utf-8")
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
            original = "/home/dylan/.hestia/artifacts/art_1234"
            path.write_text(original, encoding="utf-8")
            changed = scrub_fixture_file(path, dry_run=True)
            assert changed is True
            assert path.read_text(encoding="utf-8") == original
