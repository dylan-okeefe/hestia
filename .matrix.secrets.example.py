"""Matrix secrets scaffold — copy to `.matrix.secrets.py` and fill in.

  cp .matrix.secrets.example.py .matrix.secrets.py

`.matrix.secrets.py` is gitignored. Never commit it.

Hermes-style option: Matrix access tokens expire or rotate on some homeservers.
Keeping **LOGIN_PASSWORD** here (same account as USER_ID) lets you re-login with
`matrix-nio` (or a small script) to mint a fresh **ACCESS_TOKEN** when needed.
Hestia core does not yet auto-refresh from password; wire that yourself or wait
for a future release — the password field is for your local workflow.

Load from `config.py` (example):

    from pathlib import Path
    import importlib.util

    def _load_matrix_secrets():
        p = Path(__file__).resolve().parent / ".matrix.secrets.py"
        if not p.exists():
            return None
        spec = importlib.util.spec_from_file_location("matrix_secrets", p)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _ms = _load_matrix_secrets()
    # if _ms:
    #     matrix = MatrixConfig(
    #         homeserver=_ms.HOMESERVER,
    #         user_id=_ms.USER_ID,
    #         device_id=_ms.DEVICE_ID,
    #         access_token=_ms.ACCESS_TOKEN,
    #         allowed_rooms=list(_ms.ALLOWED_ROOMS),
    #     )
"""

from __future__ import annotations

# --- Bot (Hestia: `hestia matrix`) ---

HOMESERVER: str = "https://matrix.org"

# Full MXID of the bot account
USER_ID: str = "@your-hestia-bot:matrix.org"

DEVICE_ID: str = "hestia-bot"

# Session token for USER_ID (Element: Help → About → Access token, or login API)
ACCESS_TOKEN: str = ""

# Optional: plaintext password for USER_ID — for manual token refresh via
# matrix-nio password login (same idea as Hermes MATRIX_PASSWORD). Do not commit.
LOGIN_PASSWORD: str = ""

# Room IDs or aliases the bot may join / receive messages in (allowlist)
ALLOWED_ROOMS: list[str] = [
    # "!abcdef:matrix.org",
]

# --- Tester / driver (matrix-commander, pytest E2E) — optional second account ---

TESTER_USER_ID: str = ""
TESTER_DEVICE_ID: str = "hestia-e2e-tester"
TESTER_ACCESS_TOKEN: str = ""
TESTER_LOGIN_PASSWORD: str = ""

# Room used for scripted tests (often same as one of ALLOWED_ROOMS)
TEST_ROOM_ID: str = ""
