"""CLI command implementations for Hestia.

Auto-discovers ``cmd_*`` entry points from submodules so adding a new
command file does not require editing this re-export list.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any

__all__: list[str] = []

# Auto-discover cmd_* functions from all submodules
for _mod_info in pkgutil.iter_modules(__path__):
    if _mod_info.name.startswith("_"):
        continue
    _mod = importlib.import_module(f"{__name__}.{_mod_info.name}")
    for _name in dir(_mod):
        if _name.startswith("cmd_"):
            globals()[_name] = getattr(_mod, _name)
            __all__.append(_name)


def __getattr__(name: str) -> Any:
    """Lazy re-export of ``cli`` to avoid circular imports with ``hestia.cli``."""
    if name == "cli":
        from hestia.cli import cli as _cli
        return _cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
