"""Unit tests for CheckpointManager."""


import pytest

from hestia.tools.checkpoint import CheckpointManager


@pytest.fixture
def manager(tmp_path):
    """Create a CheckpointManager using a temp backup directory."""
    return CheckpointManager(backup_dir=tmp_path / "checkpoints")


class TestCheckpointManager:
    """Tests for CheckpointManager create/restore/discard cycle."""

    def test_create_checkpoint_hashes_files(self, manager, tmp_path):
        """Creating a checkpoint records SHA-256 hashes of the given files."""
        file_a = tmp_path / "a.txt"
        file_a.write_text("hello")

        cp = manager.create("turn-1", [str(file_a)])

        assert cp.turn_id == "turn-1"
        assert str(file_a.resolve()) in cp.file_hashes
        assert len(cp.file_hashes[str(file_a.resolve())]) == 64  # sha256 hex

    def test_create_checkpoint_hashes_directory(self, manager, tmp_path):
        """Creating a checkpoint recursively hashes all files under a directory."""
        sub = tmp_path / "project" / "src"
        sub.mkdir(parents=True)
        (sub / "main.py").write_text("print(1)")
        (sub / "util.py").write_text("def helper(): pass")

        cp = manager.create("turn-2", [str(tmp_path / "project")])

        assert len(cp.file_hashes) == 2

    def test_restore_reverts_file_content(self, manager, tmp_path):
        """After editing a file, restore brings back the original content."""
        file_x = tmp_path / "x.txt"
        file_x.write_text("original")

        manager.create("turn-3", [str(file_x)])
        file_x.write_text("modified")

        manager.restore("turn-3")

        assert file_x.read_text() == "original"

    def test_restore_reverts_directory_tree(self, manager, tmp_path):
        """Restore reverts creations, modifications, and deletions in a directory."""
        root = tmp_path / "repo"
        root.mkdir()
        (root / "a.txt").write_text("A")
        (root / "b.txt").write_text("B")

        manager.create("turn-4", [str(root)])

        # Modify, create, delete
        (root / "a.txt").write_text("A-modified")
        (root / "c.txt").write_text("C-new")
        (root / "b.txt").unlink()

        manager.restore("turn-4")

        assert (root / "a.txt").read_text() == "A"
        assert not (root / "c.txt").exists()
        assert (root / "b.txt").read_text() == "B"

    def test_discard_removes_checkpoint(self, manager, tmp_path):
        """Discarding a checkpoint makes restore impossible."""
        file_y = tmp_path / "y.txt"
        file_y.write_text("snapshot")

        manager.create("turn-5", [str(file_y)])
        file_y.write_text("changed")

        manager.discard("turn-5")

        with pytest.raises(ValueError, match="No checkpoint found"):
            manager.restore("turn-5")

    def test_discard_is_idempotent(self, manager, tmp_path):
        """Discarding a non-existent checkpoint does not raise."""
        manager.discard("turn-missing")  # should not raise

    def test_restore_unknown_turn_raises(self, manager):
        """Restoring an unknown turn raises ValueError."""
        with pytest.raises(ValueError, match="No checkpoint found"):
            manager.restore("turn-unknown")

    def test_file_hashes_match_content(self, manager, tmp_path):
        """Stored hashes are actual SHA-256 of file bytes."""
        import hashlib

        data = "checkpoint me"
        file_z = tmp_path / "z.txt"
        file_z.write_text(data)

        cp = manager.create("turn-6", [str(file_z)])

        expected = hashlib.sha256(data.encode()).hexdigest()
        assert cp.file_hashes[str(file_z.resolve())] == expected
