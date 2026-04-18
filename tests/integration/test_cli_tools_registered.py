"""Smoke test: verify read_artifact and delete_memory appear in CLI registry."""

from __future__ import annotations

import tempfile

from click.testing import CliRunner

from hestia.cli import cli


class TestCliToolsRegistered:
    """Verify new tools are reachable through the CLI bootstrap path."""

    def test_registry_contains_tools_via_callback(self) -> None:
        """Use click's invoke with a callback to capture the registry."""
        from hestia.cli import CliAppContext

        runner = CliRunner()
        with (
            tempfile.TemporaryDirectory() as artifacts_dir,
            tempfile.TemporaryDirectory() as slot_dir,
            tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f,
        ):
            db_path = f.name

            captured_registry = None

            @cli.command(name="_test_registry")
            def _test_registry() -> None:
                from click import get_current_context

                ctx = get_current_context()
                app: CliAppContext = ctx.obj["app"]
                nonlocal captured_registry
                captured_registry = app.tool_registry

            result = runner.invoke(
                cli,
                [
                    "--db-path", db_path,
                    "--artifacts-path", artifacts_dir,
                    "--slot-dir", slot_dir,
                    "_test_registry",
                ],
            )
            assert result.exit_code == 0, f"Output: {result.output}"
            assert captured_registry is not None
            assert "read_artifact" in captured_registry.list_names()
            assert "delete_memory" in captured_registry.list_names()
