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

    def _safe_name(self, domain: str) -> str:
        return domain.replace(".", "_")

    def _session_dir(self, domain: str, create: bool = True) -> Path:
        path = self.base_dir / self._safe_name(domain)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _has_session_data(self, path: Path) -> bool:
        """Return True if *path* contains a stored session file."""
        return path.is_dir() and (
            (path / "cookies.json").exists() or (path / "storage_state.json").exists()
        )

    def _find_existing_dir(self, domain: str) -> Path | None:
        """Return an existing session dir for *domain* or its www variant.

        Tries exact match first, then the domain with/without ``www.`` prefix.
        Only returns directories that actually contain session data.
        Returns ``None`` if no suitable directory exists.
        """
        candidates = [domain]
        if domain.startswith("www."):
            candidates.append(domain[4:])
        else:
            candidates.append("www." + domain)

        for cand in candidates:
            path = self.base_dir / self._safe_name(cand)
            if self._has_session_data(path):
                return path
        return None

    def save_cookies(self, domain: str, cookies: list[dict[str, Any]]) -> None:
        path = self._session_dir(domain) / "cookies.json"
        path.write_text(json.dumps(cookies, indent=2))

    def load_cookies(self, domain: str) -> list[dict[str, Any]]:
        # Try exact domain first, then www variant for backward compatibility.
        path = self._session_dir(domain, create=False) / "cookies.json"
        if path.exists():
            return cast(list[dict[str, Any]], json.loads(path.read_text()))

        existing_dir = self._find_existing_dir(domain)
        if existing_dir is not None:
            alt_path = existing_dir / "cookies.json"
            if alt_path.exists():
                return cast(list[dict[str, Any]], json.loads(alt_path.read_text()))

        return []

    def save_storage(self, domain: str, storage_state: dict[str, Any]) -> None:
        path = self._session_dir(domain) / "storage_state.json"
        path.write_text(json.dumps(storage_state, indent=2))

    def load_storage(self, domain: str) -> dict[str, Any] | None:
        # Try exact domain first, then www variant for backward compatibility.
        path = self._session_dir(domain, create=False) / "storage_state.json"
        if path.exists():
            return cast(dict[str, Any], json.loads(path.read_text()))

        existing_dir = self._find_existing_dir(domain)
        if existing_dir is not None:
            alt_path = existing_dir / "storage_state.json"
            if alt_path.exists():
                return cast(dict[str, Any], json.loads(alt_path.read_text()))

        return None

    def list_domains(self) -> list[str]:
        return [d.name.replace("_", ".") for d in self.base_dir.iterdir() if d.is_dir()]

    def clear(self, domain: str) -> None:
        shutil.rmtree(self._session_dir(domain), ignore_errors=True)
