"""L247 Phase 5A detector: the two starter-persona copies must not drift.

``src/hestia/data/SOUL.example.md`` is the canonical text (the only copy an
installed ``hestia init --with-soul`` can reach — uv_build ships only
src/hestia/). The root ``SOUL.example.md`` exists for people browsing the
repository on GitHub. Duplication that cannot be removed gets a test that
fails when the copies drift.
"""

from __future__ import annotations

from pathlib import Path

from hestia.commands.admin import _soul_template

ROOT_COPY = Path("SOUL.example.md")


def test_root_soul_example_matches_packaged_canonical() -> None:
    assert ROOT_COPY.exists(), "root SOUL.example.md is missing"
    packaged = _soul_template().encode()
    assert ROOT_COPY.read_bytes() == packaged, (
        "SOUL.example.md at the repo root has drifted from the canonical "
        "packaged copy (src/hestia/data/SOUL.example.md). Update both to "
        "the same bytes - init --with-soul and the README instruction must "
        "hand a new user the same persona."
    )


def test_init_writes_packaged_persona(tmp_path, monkeypatch):
    """hestia init --with-soul writes exactly the packaged text."""
    import asyncio

    from hestia.app import AppContext
    from hestia.commands.admin import cmd_init
    from hestia.config import HestiaConfig

    cfg = HestiaConfig.default()
    cfg.storage.artifacts_dir = tmp_path / "artifacts"
    cfg.slots.slot_dir = tmp_path / "slots"
    app = AppContext(cfg)
    monkeypatch.chdir(tmp_path)
    asyncio.run(cmd_init(app, with_soul=True))
    written = (tmp_path / "SOUL.md").read_bytes()
    assert written == _soul_template().encode()
