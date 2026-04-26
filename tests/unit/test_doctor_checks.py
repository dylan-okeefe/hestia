"""Green and red path tests for hestia doctor checks."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from hestia.doctor import (
    _check_config_file_loads,
    _check_config_schema,
    _check_dependencies_in_sync,
    _check_llamacpp_reachable,
    _check_memory_epoch,
    _check_platform_prereqs,
    _check_python_version,
    _check_sqlite_dbs_readable,
    _check_trust_preset_resolves,
)


@pytest.fixture
def make_app(tmp_path):
    """Build a minimal CliAppContext for doctor tests."""

    def _factory(cfg=None):
        from hestia.app import AppContext
        from hestia.config import HestiaConfig
        from hestia.persistence.db import Database
        if cfg is None:
            cfg = HestiaConfig.default()
        cfg.storage.database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
        cfg.storage.artifacts_dir = tmp_path / "artifacts"
        app = AppContext(cfg)
        return app

    return _factory


class TestPythonVersion:
    """Tests for _check_python_version."""

    async def test_python_version_ok(self, monkeypatch, make_app):
        """Current Python is >= 3.11."""
        app = make_app()
        result = await _check_python_version(app)
        assert result.ok is True

    async def test_python_version_too_old(self, monkeypatch, make_app):
        """Monkeypatch sys.version_info to an old version."""
        app = make_app()
        monkeypatch.setattr("sys.version_info", (3, 9, 0))
        result = await _check_python_version(app)
        assert result.ok is False
        assert "3.9" in result.detail
        assert "need 3.11 or newer" in result.detail


class TestDependenciesInSync:
    """Tests for _check_dependencies_in_sync."""

    async def test_uv_pip_check_ok(self, monkeypatch, make_app):
        """Simulate uv pip check returning exit 0."""
        app = make_app()

        class _FakeProc:
            returncode = 0

            async def communicate(self):
                return (b"", b"")

        async def fake_exec(*args, **kwargs):
            return _FakeProc()

        monkeypatch.setattr("hestia.doctor.asyncio.create_subprocess_exec", fake_exec)
        result = await _check_dependencies_in_sync(app)
        assert result.ok is True

    async def test_uv_pip_check_reports_drift(self, monkeypatch, make_app):
        """Simulate uv pip check returning non-zero with output."""
        app = make_app()

        class _FakeProc:
            returncode = 1

            async def communicate(self):
                return (
                    b"package-a has incompatible dependency\nline2\nline3\nline4\nline5\nline6",
                    b"",
                )

        async def fake_exec(*args, **kwargs):
            return _FakeProc()

        monkeypatch.setattr("hestia.doctor.asyncio.create_subprocess_exec", fake_exec)
        result = await _check_dependencies_in_sync(app)
        assert result.ok is False
        assert "package-a" in result.detail
        assert result.detail.count("\n") == 4

    async def test_uv_not_on_path(self, monkeypatch, make_app):
        """Simulate uv not being found on PATH."""
        app = make_app()

        async def fake_exec(*args, **kwargs):
            raise FileNotFoundError("uv")

        monkeypatch.setattr("hestia.doctor.asyncio.create_subprocess_exec", fake_exec)
        result = await _check_dependencies_in_sync(app)
        assert result.ok is False
        assert "uv not found on PATH" in result.detail


class TestConfigFileLoads:
    """Tests for _check_config_file_loads."""

    async def test_config_file_loads_ok(self, make_app):
        """Smoke test on a normal AppContext."""
        app = make_app()
        result = await _check_config_file_loads(app)
        assert result.ok is True
        assert "loaded from" in result.detail


class TestConfigSchema:
    """Tests for _check_config_schema."""

    async def test_config_schema_ok_when_field_missing(self, make_app):
        """When schema_version doesn't exist, returns ok with expected detail."""
        app = make_app()
        result = await _check_config_schema(app)
        assert result.ok is True
        assert "schema_version not yet defined" in result.detail


class TestSQLiteDBsReadable:
    """Tests for _check_sqlite_dbs_readable."""

    async def test_sqlite_dbs_readable_ok(self, make_app):
        """Use temp SQLite database."""
        app = make_app()
        result = await _check_sqlite_dbs_readable(app)
        assert result.ok is True
        assert ": ok" in result.detail

    async def test_sqlite_dbs_readable_reports_corruption(self, make_app, tmp_path):
        """Write garbage bytes to the db file and assert ok=False."""
        cfg = make_app().config
        db_path = tmp_path / "corrupt.db"
        db_path.write_bytes(b"NOT A SQLITE DB")
        cfg.storage.database_url = f"sqlite+aiosqlite:///{db_path}"

        from hestia.app import AppContext

        app = AppContext(cfg)
        result = await _check_sqlite_dbs_readable(app)
        assert result.ok is False


class TestLlamaCppReachable:
    """Tests for _check_llamacpp_reachable."""

    async def test_llamacpp_reachable_skipped_when_no_base_url(self, make_app):
        """When base_url is empty, check is skipped."""
        app = make_app()
        app.config.inference.base_url = ""
        result = await _check_llamacpp_reachable(app)
        assert result.ok is True
        assert "no inference base_url configured" in result.detail

    async def test_llamacpp_reachable_ok(self, monkeypatch, make_app):
        """Mock AsyncClient.get to return 200."""
        app = make_app()
        app.config.inference.base_url = "http://localhost:8001"

        class _FakeResponse:
            status_code = 200

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                return _FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        result = await _check_llamacpp_reachable(app)
        assert result.ok is True
        assert "200" in result.detail

    async def test_llamacpp_reachable_timeout(self, monkeypatch, make_app):
        """Mock AsyncClient.get to raise TimeoutException."""
        app = make_app()
        app.config.inference.base_url = "http://localhost:8001"

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        result = await _check_llamacpp_reachable(app)
        assert result.ok is False
        assert "did not respond within 2s" in result.detail

    async def test_llamacpp_reachable_connection_error(self, monkeypatch, make_app):
        """Mock AsyncClient.get to raise ConnectError."""
        app = make_app()
        app.config.inference.base_url = "http://localhost:8001"

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
        result = await _check_llamacpp_reachable(app)
        assert result.ok is False
        assert "cannot connect to llama.cpp" in result.detail


class TestPlatformPrereqs:
    """Tests for _check_platform_prereqs."""

    async def test_platform_prereqs_telegram_missing_token(self, make_app):
        """Telegram enabled (allowed_users set) but missing bot_token."""
        from hestia.config import HestiaConfig

        cfg = HestiaConfig.default()
        cfg.telegram.allowed_users = ["12345"]
        app = make_app(cfg)
        result = await _check_platform_prereqs(app)
        assert result.ok is False
        assert "telegram: bot_token not set" in result.detail

    async def test_platform_prereqs_email_password_env_missing(self, make_app):
        """Email enabled but password_env points to missing env var."""
        from hestia.config import HestiaConfig

        cfg = HestiaConfig.default()
        cfg.email.imap_host = "imap.example.com"
        cfg.email.username = "user@example.com"
        cfg.email.password_env = "MISSING_EMAIL_PASSWORD"
        app = make_app(cfg)
        result = await _check_platform_prereqs(app)
        assert result.ok is False
        assert "password_env not resolved" in result.detail

class TestTrustPresetResolves:
    """Tests for _check_trust_preset_resolves."""

    async def test_trust_preset_resolves_known(self, make_app):
        """Known preset name passes."""
        from hestia.config import HestiaConfig, TrustConfig

        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig(preset="household")
        app = make_app(cfg)
        result = await _check_trust_preset_resolves(app)
        assert result.ok is True
        assert "household" in result.detail

    async def test_trust_preset_resolves_unknown_preset_name(self, make_app):
        """Unknown preset name fails."""
        from hestia.config import HestiaConfig, TrustConfig

        cfg = HestiaConfig.default()
        cfg.trust = TrustConfig(preset="not_a_preset")
        app = make_app(cfg)
        result = await _check_trust_preset_resolves(app)
        assert result.ok is False
        assert "unknown trust preset" in result.detail


class TestMemoryEpoch:
    """Tests for _check_memory_epoch."""

    async def test_memory_epoch_ok(self, make_app, tmp_path):
        """Epoch file exists and contains an int."""
        epoch_file = tmp_path / "epoch.txt"
        epoch_file.write_text("42")

        app = make_app()

        @dataclass
        class FakeMemoryConfig:
            epoch_path: str = str(epoch_file)

        app.config.memory = FakeMemoryConfig()  # type: ignore[attr-defined]
        result = await _check_memory_epoch(app)
        assert result.ok is True
        assert ": ok" in result.detail

    async def test_memory_epoch_missing_file(self, make_app, tmp_path):
        """Epoch file does not exist."""
        epoch_file = tmp_path / "epoch.txt"

        app = make_app()

        @dataclass
        class FakeMemoryConfig:
            epoch_path: str = str(epoch_file)

        app.config.memory = FakeMemoryConfig()  # type: ignore[attr-defined]
        result = await _check_memory_epoch(app)
        assert result.ok is False
        assert "file not found" in result.detail

    async def test_memory_epoch_unparseable(self, make_app, tmp_path):
        """Epoch file contains non-integer text."""
        epoch_file = tmp_path / "epoch.txt"
        epoch_file.write_text("not-a-number")

        app = make_app()

        @dataclass
        class FakeMemoryConfig:
            epoch_path: str = str(epoch_file)

        app.config.memory = FakeMemoryConfig()  # type: ignore[attr-defined]
        result = await _check_memory_epoch(app)
        assert result.ok is False
        assert "do not parse as int" in result.detail
