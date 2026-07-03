"""Context passed to external tool module setup hooks."""

from __future__ import annotations

from dataclasses import dataclass

from hestia.config import HestiaConfig
from hestia.persistence.db import Database


@dataclass
class ExternalToolModuleContext:
    """Narrow context given to external tool module ``setup`` hooks.

    This intentionally exposes only the database handle and top-level config.
    Passing the full :class:`~hestia.app.AppContext` would give external modules
    unrestricted access to every subsystem, so the seam is kept small.

    Warning: handing a database connection to an external module is a wide
    trust grant. Only list modules you fully control in ``extra_tool_modules``.
    """

    db: Database
    config: HestiaConfig
