#!/usr/bin/env python3
"""Scrub sensitive/local data out of regression fixtures before committing.

The regression collector intentionally captures real model output, which can
include absolute paths, user names, email addresses, tokens, or other local
data. This script sanitizes fixtures under ``tests/fixtures/regression/`` so
they are safe to commit and portable across machines.

Run it manually:

    .venv/bin/python scripts/scrub_regression_fixtures.py

Run in check mode (exit non-zero if any fixture needs scrubbing):

    .venv/bin/python scripts/scrub_regression_fixtures.py --check

To auto-scrub fixtures as they are collected, set the environment variable:

    HESTIA_REGRESSION_AUTO_SCRUB=1

You can also install it as a pre-commit hook:

    cp scripts/scrub_regression_fixtures.py .git/hooks/pre-commit-scrub
    # Then make your .git/hooks/pre-commit run it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hestia.diagnostics.scrub import scrub_fixture_file, scrub_text


DEFAULT_FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "regression"


def scrub_directory(directory: Path, *, dry_run: bool = False) -> int:
    """Scrub all fixture files under ``directory``. Returns number changed."""
    changed = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".xml", ".txt", ".md"}:
            continue
        if scrub_fixture_file(path, dry_run=dry_run):
            changed += 1
            action = "would scrub" if dry_run else "scrubbed"
            print(f"{action}: {path.relative_to(directory.parent)}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scrub local/sensitive data from regression fixtures."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help="Directory containing fixtures to scrub.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any fixture needs scrubbing, but do not write changes.",
    )
    args = parser.parse_args(argv)

    directory = args.directory.expanduser().resolve()
    if not directory.exists():
        print(f"Fixture directory does not exist: {directory}")
        return 0

    changed = scrub_directory(directory, dry_run=args.check)
    if args.check and changed:
        print(
            f"\n{changed} fixture(s) need scrubbing. "
            "Run without --check to apply changes."
        )
        return 1

    print(f"\n{changed} fixture(s) scrubbed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
