"""Read-clipboard tool."""

import asyncio
import shutil
import sys

from hestia.tools.metadata import tool


async def _run(args: list[str]) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


@tool(
    name="read_clipboard",
    public_description="Read the current contents of the system clipboard.",
    parameters_schema={
        "type": "object",
        "properties": {},
    },
    max_inline_chars=2000,
    tags=["utility"],
    capabilities=[],
)
async def read_clipboard() -> str:
    """Read the system clipboard, trying common providers across platforms."""
    candidates: list[list[str]] = []

    if sys.platform == "darwin":
        candidates.append(["pbpaste"])
    elif sys.platform == "win32":
        candidates.append([
            "powershell.exe",
            "-command",
            "Get-Clipboard",
        ])
    else:
        # Linux / BSD
        if shutil.which("wl-paste"):
            candidates.append(["wl-paste"])
        if shutil.which("xclip"):
            candidates.append(["xclip", "-selection", "clipboard", "-o"])
        if shutil.which("xsel"):
            candidates.append(["xsel", "--clipboard", "--output"])

    errors: list[str] = []
    for args in candidates:
        result = await _run(args)
        if result is not None:
            return result.strip()
        errors.append(args[0])

    if not candidates:
        return "No clipboard provider found (tried wl-paste, xclip, xsel)."
    return (
        "Could not read clipboard. Tried: "
        + ", ".join(errors)
        + ". Ensure a clipboard utility is installed and a display/session is available."
    )
