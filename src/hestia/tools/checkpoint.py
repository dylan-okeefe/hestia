"""Per-turn file checkpointing for safe rollback.

A lightweight snapshot keyed to turn id.  For git repos we try ``git stash``
first; for non-git trees we fall back to a recursive file copy into a temp
backup directory.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from hestia.core.clock import utcnow

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Snapshot of file state at the start of a turn."""

    turn_id: str
    created_at: datetime
    file_hashes: dict[str, str]  # path → sha256 of content at checkpoint time
    original_paths: list[str] = field(default_factory=list)
    backup_dir: Path | None = None
    git_root: Path | None = None
    git_stash_ref: str | None = None


class CheckpointManager:
    """Creates, restores, and discards per-turn file checkpoints."""

    def __init__(self, backup_dir: Path | None = None) -> None:
        self._backup_dir = backup_dir or Path(tempfile.gettempdir()) / "hestia-checkpoints"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints: dict[str, Checkpoint] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, turn_id: str, paths: list[str]) -> Checkpoint:
        """Snapshot current state of *paths* (files or directories)."""
        resolved = [Path(p).resolve() for p in paths]
        file_hashes: dict[str, str] = {}

        for p in resolved:
            if p.is_file():
                file_hashes[str(p)] = self._sha256(p)
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        file_hashes[str(f)] = self._sha256(f)

        git_root = self._find_common_git_root(resolved)
        if git_root is not None:
            try:
                cp = self._create_git_checkpoint(turn_id, resolved, git_root, file_hashes)
                self._checkpoints[turn_id] = cp
                return cp
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Git checkpoint failed for turn %s; falling back to file copy", turn_id
                )

        cp = self._create_file_checkpoint(turn_id, resolved, file_hashes)
        self._checkpoints[turn_id] = cp
        return cp

    def restore(self, turn_id: str) -> None:
        """Restore all paths to their checkpointed state."""
        cp = self._checkpoints.get(turn_id)
        if cp is None:
            raise ValueError(f"No checkpoint found for turn {turn_id}")

        if cp.git_stash_ref and cp.git_root:
            self._restore_git(cp)
        elif cp.backup_dir:
            self._restore_file(cp)
        else:
            logger.warning("Checkpoint %s has no restore mechanism", turn_id)

    def discard(self, turn_id: str) -> None:
        """Remove checkpoint data (idempotent)."""
        cp = self._checkpoints.pop(turn_id, None)
        if cp is None:
            return

        if cp.git_stash_ref and cp.git_root:
            self._discard_git(cp)
        elif cp.backup_dir and cp.backup_dir.exists():
            shutil.rmtree(cp.backup_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _create_git_checkpoint(
        self,
        turn_id: str,
        paths: list[Path],
        git_root: Path,
        file_hashes: dict[str, str],
    ) -> Checkpoint:
        # Only stash if the working tree is dirty.
        status = subprocess.run(
            ["git", "-C", str(git_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        stash_ref: str | None = None
        if status.stdout.strip():
            subprocess.run(
                ["git", "-C", str(git_root), "stash", "push", "-m", f"hestia-checkpoint-{turn_id}"],
                capture_output=True,
                check=True,
            )
            stash_ref = self._find_stash_ref(git_root, turn_id)

        return Checkpoint(
            turn_id=turn_id,
            created_at=utcnow(),
            file_hashes=file_hashes,
            original_paths=[str(p) for p in paths],
            git_root=git_root,
            git_stash_ref=stash_ref,
        )

    def _restore_git(self, cp: Checkpoint) -> None:
        assert cp.git_root is not None
        assert cp.git_stash_ref is not None
        subprocess.run(
            ["git", "-C", str(cp.git_root), "stash", "pop", cp.git_stash_ref],
            capture_output=True,
            check=True,
        )

    def _discard_git(self, cp: Checkpoint) -> None:
        assert cp.git_root is not None
        assert cp.git_stash_ref is not None
        with contextlib.suppress(subprocess.CalledProcessError):
            subprocess.run(
                ["git", "-C", str(cp.git_root), "stash", "drop", cp.git_stash_ref],
                capture_output=True,
                check=True,
            )

    def _find_stash_ref(self, git_root: Path, turn_id: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(git_root), "stash", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if f"hestia-checkpoint-{turn_id}" in line:
                return line.split(":")[0]
        return None

    # ------------------------------------------------------------------
    # File-copy helpers
    # ------------------------------------------------------------------

    def _create_file_checkpoint(
        self,
        turn_id: str,
        paths: list[Path],
        file_hashes: dict[str, str],
    ) -> Checkpoint:
        turn_backup = self._backup_dir / turn_id
        turn_backup.mkdir(parents=True, exist_ok=True)

        for p in paths:
            if p.is_file():
                dest = self._backup_path(p, turn_backup)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        dest = self._backup_path(f, turn_backup)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, dest)

        return Checkpoint(
            turn_id=turn_id,
            created_at=utcnow(),
            file_hashes=file_hashes,
            original_paths=[str(p) for p in paths],
            backup_dir=turn_backup,
        )

    def _restore_file(self, cp: Checkpoint) -> None:
        assert cp.backup_dir is not None

        backed_up_files = set(cp.file_hashes.keys())

        for path_str in cp.original_paths:
            path = Path(path_str)
            if path.is_file():
                if str(path) in backed_up_files:
                    dest = self._backup_path(path, cp.backup_dir)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, path)
                else:
                    if path.exists():
                        path.unlink()
            elif path.is_dir():
                current_files = {str(f) for f in path.rglob("*") if f.is_file()}

                # Delete files created after checkpoint
                for f in current_files - backed_up_files:
                    Path(f).unlink()

                # Restore files that existed at checkpoint (modified or deleted)
                for f in backed_up_files:
                    orig = Path(f)
                    backup = self._backup_path(orig, cp.backup_dir)
                    orig.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, orig)

                # Clean up empty directories
                self._cleanup_empty_dirs(path)

    @staticmethod
    def _backup_path(original: Path, backup_dir: Path) -> Path:
        """Map an absolute path to its mirrored location under *backup_dir*."""
        try:
            rel = original.relative_to(Path("/"))
        except ValueError:
            rel = original
        return backup_dir / rel

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    @staticmethod
    def _find_git_root(path: Path) -> Path | None:
        try:
            cwd = str(path) if path.is_dir() else str(path.parent)
            result = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(result.stdout.strip()).resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _find_common_git_root(self, paths: list[Path]) -> Path | None:
        roots: set[Path | None] = {self._find_git_root(p) for p in paths}
        roots.discard(None)
        if len(roots) == 1:
            return roots.pop()
        return None

    @staticmethod
    def _cleanup_empty_dirs(dir_path: Path) -> None:
        for root, dirs, _files in os.walk(str(dir_path), topdown=False):
            for d in dirs:
                p = Path(root) / d
                try:
                    if p.exists() and not any(p.iterdir()):
                        p.rmdir()
                except OSError:
                    pass
