"""L247 Phase 5B: startup says what it could not find.

Drives the real startup path (``make_app``) — the checks live in
``_report_startup_status`` and are not reimplemented here.
"""

from __future__ import annotations

from pathlib import Path

from hestia.app import make_app, platform_credential_gaps
from hestia.config import EmailConfig, HestiaConfig, MatrixConfig, StorageConfig


def _runtime_config(tmp_path: Path) -> HestiaConfig:
    cfg = HestiaConfig.default()
    cfg.storage = StorageConfig(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/fresh.db",
        artifacts_dir=tmp_path / "artifacts",
    )
    return cfg


def test_enabled_platform_with_missing_credentials_warns_and_continues(
    tmp_path, monkeypatch, capsys
) -> None:
    """5B-1: each enabled platform names its own missing credential and
    startup proceeds (make_app does not raise)."""
    cfg = _runtime_config(tmp_path)
    cfg.matrix = MatrixConfig(
        access_token="tok", user_id="", homeserver=""
    )
    cfg.email = EmailConfig(
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        password="",
        password_env=None,
    )

    app = make_app(cfg)

    err = capsys.readouterr().err
    assert "Matrix is enabled but matrix.user_id is missing" in err
    assert "matrix.homeserver is missing" in err
    assert "Email is enabled but no password is configured" in err
    # Startup continued: the app context exists. EmailAdapter still builds
    # (it fails at send time, not construction) - the gap is what 5B adds.
    assert app is not None


def test_matrix_gap_helper_is_structured_by_platform(tmp_path) -> None:
    """Gaps carry a stable platform key - serve.py branches on it, never on
    message text (review P7: rewording a message must not flip behavior)."""
    cfg = _runtime_config(tmp_path)
    cfg.matrix = MatrixConfig(access_token="tok", user_id="", homeserver="")
    gaps = platform_credential_gaps(cfg)
    matrix_gaps = [g for g in gaps if g.platform == "matrix"]
    assert matrix_gaps, "incomplete Matrix must produce a matrix-keyed gap"
    assert all("matrix.user_id" in g.message or "matrix.homeserver" in g.message for g in matrix_gaps)


def test_relative_sqlite_url_resolves_inside_cwd(tmp_path, monkeypatch, capsys) -> None:
    """Review P6: three-slash SQLite URLs are RELATIVE. The default config
    uses `sqlite+aiosqlite:///hestia.db`; hand-parsing resolved that to
    /hestia.db and produced a false alarm on every boot. The notice must
    name the path relative to the working directory."""
    monkeypatch.chdir(tmp_path)
    cfg = _runtime_config(tmp_path)
    cfg.storage.database_url = "sqlite+aiosqlite:///hestia.db"
    make_app(cfg)
    out = capsys.readouterr().out + capsys.readouterr().err
    expected = tmp_path / "hestia.db"
    assert f"No existing database at {expected}" in out


def test_in_memory_database_gets_no_notice(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = HestiaConfig.default()
    cfg.storage.database_url = "sqlite+aiosqlite:///:memory:"
    make_app(cfg)
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "No existing database at" not in out


def test_absent_database_names_full_resolved_path(tmp_path, monkeypatch, capsys) -> None:
    """5B-2: creating a database from scratch announces the resolved path,
    unremarkably - informative to someone who expected existing history."""
    (tmp_path / "nested").mkdir()
    db_file = tmp_path / "nested" / "fresh.db"
    cfg = HestiaConfig.default()
    cfg.storage = StorageConfig(
        database_url=f"sqlite+aiosqlite:///{db_file}",
        artifacts_dir=tmp_path / "artifacts",
    )
    make_app(cfg)
    out = capsys.readouterr().out + capsys.readouterr().err
    assert f"No existing database at {db_file}" in out
    assert "creating a new one" in out


def test_existing_database_is_not_announced(tmp_path, capsys) -> None:
    """A populated deploy must not get the creation line on every boot."""
    cfg = _runtime_config(tmp_path)
    make_app(cfg)
    capsys.readouterr()
    # Simulate a populated deploy: the file exists at the resolved path.
    # (make_app itself does not create the file; bootstrap does.)
    Path(cfg.storage.database_url.split("://", 1)[1]).touch()
    make_app(cfg)
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "No existing database at" not in out
