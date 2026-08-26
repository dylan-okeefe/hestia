"""L248/#58 round 4 detector: every scheduler's tick is wired or exempted.

Two guarantees:
1. ENUMERATION is dynamic - every module under src/hestia matching
   *scheduler* in any path segment OR living inside the scheduler package
   is imported (rglob over the whole src tree) and scanned for classes defining an
   ``async def tick``; a newly added scheduler is picked up automatically.
2. ANCHORING - file targets are resolved from this test's own location,
   not the working directory (the A2 defect shape: right answer from one
   cwd, wrong from another).

Each discovered scheduler class must expose ``tick_loop`` AND be started
from serve's wiring (textual assertion; the wiring IS the text) or be
listed in DAEMON_ONLY with a reason.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVE_PATH = REPO_ROOT / "src" / "hestia" / "commands" / "serve.py"
DAEMON_PATH = REPO_ROOT / "src" / "hestia" / "commands" / "scheduler.py"

# Schedulers that intentionally do NOT run under serve, with the reason.
DAEMON_ONLY: dict[str, str] = {}

def _discover_tick_classes() -> dict[str, set[str]]:
    """Return {module_dotted_name: {class names with async tick}}.

    Enumeration is filesystem-driven so a new scheduler module is found
    without editing this test.
    """
    src_root = REPO_ROOT / "src" / "hestia"  # whole tree, any filename
    discovered: dict[str, set[str]] = {}
    # Widen the net: match scheduler-named files AND anything inside the
    # scheduler package (engine.py lives there), so a tick class in an
    # innocuously-named file is still discovered.
    for path in list(src_root.rglob("*scheduler*.py")) + list(
        (src_root / "scheduler").glob("*.py")
    ):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        dotted = ".".join(
            ["hestia", *path.relative_to(src_root).with_suffix("").parts]
        )
        if dotted.endswith(".__init__"):
            continue
        try:
            module = importlib.import_module(dotted)
        except Exception as exc:  # noqa: BLE001 — report, don't crash enumeration
            raise AssertionError(
                f"could not import scheduler module {dotted}: {exc}"
            ) from exc
        # Simpler, robust check: textual presence inside the class source.
        classes = {
            name
            for name, obj in vars(module).items()
            if inspect.isclass(obj)
            and obj.__module__ == dotted
            and "async def tick(" in inspect.getsource(obj)
        }
        if classes:
            discovered[dotted] = classes
    return discovered


def test_every_scheduler_class_is_wired_or_exempt() -> None:
    """Enumeration guarantee: no scheduler class can hide from the gate."""
    serve_src = SERVE_PATH.read_text()
    DAEMON_PATH.read_text()  # daemon parity asserted in its own test below

    problems: list[str] = []
    for dotted, classes in sorted(_discover_tick_classes().items()):
        for cls in sorted(classes):
            # The wiring check matches on the class stem: a variable named
            # reflection_scheduler / style_scheduler calling .tick_loop(.
            stem = cls.lower().replace("scheduler", "").strip()
            # A class named exactly `Scheduler` yields an empty stem whose
            # \w*\w* pattern would match ANY .tick_loop( call - auto-pass
            # trap. Fall back to the full lowercase class name.
            if not stem:
                stem = cls.lower()
            generic = re.search(rf"\w*{stem}\w*\.tick_loop\(", serve_src)
            daemon_only = cls in DAEMON_ONLY
            if not (generic or daemon_only):
                problems.append(
                    f"{dotted}.{cls} defines async tick() but is neither "
                    "started from serve nor listed in DAEMON_ONLY"
                )
            if generic and cls in DAEMON_ONLY:
                problems.append(
                    f"{cls} is listed daemon-only but serve wires it"
                )
    assert not problems, "\n".join(problems)


def test_daemon_and_serve_share_the_one_tick_site() -> None:
    """The daemon must run schedulers via tick_loop too - no second
    hand-rolled tick implementation."""
    src = DAEMON_PATH.read_text()
    assert ".tick_loop(" in src
    assert "reflection_scheduler.tick()" not in src.replace(".tick_loop(", "")


def test_detector_paths_are_anchored_to_this_file() -> None:
    """A2-shape guard: the detector's own targets must resolve from any cwd."""
    assert SERVE_PATH == REPO_ROOT / "src" / "hestia" / "commands" / "serve.py"
    assert SERVE_PATH.exists()


def test_configured_tick_interval_is_used_for_reflection_and_style() -> None:
    """R4-5: the dead knob is dead no more. Both entry points must pass
    config.scheduler.tick_interval_seconds into tick_loop."""
    serve_src = SERVE_PATH.read_text()
    daemon_src = DAEMON_PATH.read_text()
    assert "tick_loop(interval_seconds=tick_interval)" in serve_src, (
        "serve must pass config.scheduler.tick_interval_seconds to tick_loop"
    )
    assert "tick_loop(interval_seconds=tick_interval)" in daemon_src, (
        "daemon must pass config.scheduler.tick_interval_seconds to tick_loop"
    )


def test_tick_interval_over_due_window_warns() -> None:
    """R4-5 safety: an interval >= the 2-minute due window can silently
    starve reflection/style; both entry points must warn."""
    for src_path in (SERVE_PATH, DAEMON_PATH):
        src = src_path.read_text()
        assert "is >= the 2-minute reflection/style due window" in src, (
            f"{src_path} must warn when tick interval >= 120s"
        )
