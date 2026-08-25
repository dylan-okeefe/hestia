"""L248/#58 round 3, R3-6 detector: every background scheduler's tick is
reached from serve's startup path through the ONE tick site
(``Scheduler.tick_loop``), or is explicitly daemon-only.

The reflection bug this guards against shipped because serve never called
the reflection/style tick loops and nothing could see it. Textual asserts
are deliberate: the wiring IS the text.
"""

from __future__ import annotations

from pathlib import Path

SERVE = Path("src/hestia/commands/serve.py")
DAEMON = Path("src/hestia/commands/scheduler.py")


def test_serve_runs_both_tick_loops() -> None:
    src = SERVE.read_text()
    assert "reflection_scheduler.tick_loop()" in src, (
        "serve must start the ReflectionScheduler tick loop"
    )
    assert "style_scheduler.tick_loop()" in src, (
        "serve must start the StyleScheduler tick loop"
    )


def test_daemon_uses_the_same_tick_site() -> None:
    src = DAEMON.read_text()
    assert "tick_loop()" in src, (
        "the standalone daemon must run schedulers via tick_loop too - "
        "no second hand-rolled tick implementation"
    )
    # The old duplicated inline ticks are gone.
    assert "reflection_scheduler.tick()" not in src.replace("tick_loop()", "")


def test_both_schedulers_expose_tick_loop() -> None:
    from hestia.reflection.scheduler import ReflectionScheduler
    from hestia.style.scheduler import StyleScheduler

    assert hasattr(ReflectionScheduler, "tick_loop")
    assert hasattr(StyleScheduler, "tick_loop")
