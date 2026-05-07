"""Persistent browser session storage using Playwright."""

import json
import shutil
from pathlib import Path
from typing import Any, cast


class BrowserSessionStore:
    """Manages persistent browser contexts for authenticated sites.

    Stores cookies and localStorage per-domain under
    ``~/.hestia/browser-sessions/<domain>/`` so logins survive restarts.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.home() / ".hestia" / "browser-sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, domain: str) -> Path:
        safe = domain.replace(".", "_")
        path = self.base_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_cookies(self, domain: str, cookies: list[dict[str, Any]]) -> None:
        path = self._session_dir(domain) / "cookies.json"
        path.write_text(json.dumps(cookies, indent=2))

    def load_cookies(self, domain: str) -> list[dict[str, Any]]:
        path = self._session_dir(domain) / "cookies.json"
        if not path.exists():
            return []
        return cast(list[dict[str, Any]], json.loads(path.read_text()))

    def save_storage(self, domain: str, storage_state: dict[str, Any]) -> None:
        path = self._session_dir(domain) / "storage_state.json"
        path.write_text(json.dumps(storage_state, indent=2))

    def load_storage(self, domain: str) -> dict[str, Any] | None:
        path = self._session_dir(domain) / "storage_state.json"
        if not path.exists():
            return None
        return cast(dict[str, Any], json.loads(path.read_text()))

    def list_domains(self) -> list[str]:
        return [d.name.replace("_", ".") for d in self.base_dir.iterdir() if d.is_dir()]

    def clear(self, domain: str) -> None:
        shutil.rmtree(self._session_dir(domain), ignore_errors=True)
