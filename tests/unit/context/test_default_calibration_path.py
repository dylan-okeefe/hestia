"""L247 regression: the ContextBuilder default calibration path resolves.

The default was computed with one parent too few from
src/hestia/context/, resolving to <repo>/src/docs/calibration.json and
printing "Calibration file not found" on every scripted use even though
docs/calibration.json exists. app.py's copy of the constant sits one
level shallower and was never wrong — do not deduplicate them without
solving the import cycle (see the comment on _DEFAULT_CALIBRATION_PATH).
"""

from pathlib import Path

from hestia.context.builder import _DEFAULT_CALIBRATION_PATH


def test_default_calibration_path_exists() -> None:
    repo_root = Path(__file__).parents[3]
    assert repo_root / "docs" / "calibration.json" == _DEFAULT_CALIBRATION_PATH
    assert _DEFAULT_CALIBRATION_PATH.exists(), (
        f"default calibration path does not exist: {_DEFAULT_CALIBRATION_PATH}"
    )
