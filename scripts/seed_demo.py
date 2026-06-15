#!/usr/bin/env python3
"""Seed the ~/Hestia demo instance with synthetic data.

This script is local tooling only. It loads ``config.demo.py`` and writes to the
demo database under ``./demo-data/``. It never touches ``~/Hestia-runtime`` or
the personal ``hestia.db``.

Run after copying ``config.demo.example.py`` to ``config.demo.py``:

    uv run python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hestia.app import AppContext, make_app
from hestia.config import HestiaConfig
from hestia.core.types import Message
from hestia.reflection.types import Proposal, ProposalStatus

DEMO_PLATFORM = "demo"
DEMO_PLATFORM_USER = "demo-admin@hestia.local"
DEMO_DISPLAY_NAME = "Demo Admin"
DEMO_SOUL = """# Demo identity

You are helping a fictional user named Demo Admin. Demo Admin is interested in
local-first AI assistants, hiking, and the color teal. They are working on a
fictional project called Acme Widgets.

## Tone
- Warm but concise.
- Uses first person ("I") when speaking about yourself.

## Context
- Operator name: Demo Admin
- Preferred language: English
- Timezone: America/New_York
"""

DEMO_MEMORIES = [
    ("Demo Admin is learning about local-first AI assistants.", ["interests"]),
    ("Demo Admin's favorite color is teal.", ["preferences"]),
    ("Demo Admin is working on a fictional project called Acme Widgets.", ["projects"]),
    ("Demo Admin prefers concise replies with bullet points.", ["style"]),
]

DEMO_MESSAGES = [
    Message(role="user", content="What can you help me with?"),
    Message(
        role="assistant",
        content=(
            "I can help with research, writing, coding, and organizing tasks. "
            "Just tell me what you'd like to work on."
        ),
    ),
]


async def _ensure_soul_file(soul_path: Path) -> None:
    """Write a bland demo SOUL.md if one does not exist."""
    if soul_path.exists():
        return
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(DEMO_SOUL, encoding="utf-8")
    print(f"Wrote demo identity to {soul_path}")


async def _ensure_demo_user(app: AppContext) -> str:
    """Return the demo admin user id, creating it if necessary."""
    existing = await app.user_store.get_user_by_identity(DEMO_PLATFORM, DEMO_PLATFORM_USER)
    if existing is not None:
        print(f"Demo admin already exists: {existing.id}")
        return existing.id

    user = await app.user_store.create_user(
        display_name=DEMO_DISPLAY_NAME,
        role="admin",
        trust_preset=None,
        notes="Synthetic admin user for local screenshots and demos.",
    )
    await app.user_store.add_identity(
        user.id,
        platform=DEMO_PLATFORM,
        platform_user=DEMO_PLATFORM_USER,
        verified=True,
    )
    print(f"Created demo admin: {user.id} ({DEMO_PLATFORM_USER})")
    return user.id


async def _ensure_memories(app: AppContext) -> None:
    """Seed synthetic memories for the demo user if none exist."""
    existing = await app.memory_store.list_memories(
        tag=None,
        limit=1,
        platform=DEMO_PLATFORM,
        platform_user=DEMO_PLATFORM_USER,
    )
    if existing:
        print("Demo memories already present; skipping.")
        return

    for content, tags in DEMO_MEMORIES:
        await app.memory_store.save(
            content=content,
            tags=tags,
            platform=DEMO_PLATFORM,
            platform_user=DEMO_PLATFORM_USER,
            session_id=None,
        )
    print(f"Seeded {len(DEMO_MEMORIES)} demo memories.")


async def _ensure_sample_session(app: AppContext) -> None:
    """Create one sample session for the demo user if none exist."""
    sessions = await app.session_store.list_sessions(
        limit=1,
        platform=DEMO_PLATFORM,
        platform_user=DEMO_PLATFORM_USER,
    )
    if sessions:
        print("Demo session already present; skipping.")
        return

    session = await app.session_store.create_session(
        platform=DEMO_PLATFORM,
        platform_user=DEMO_PLATFORM_USER,
        title="Sample demo session",
    )
    for msg in DEMO_MESSAGES:
        await app.session_store.append_message(session.id, msg)
    print(f"Created demo session: {session.id}")


async def _ensure_sample_proposal(app: AppContext) -> None:
    """Create one sample proposal if the proposals table is empty."""
    existing = await app.proposal_store.list_by_status(limit=1)
    if existing:
        print("Demo proposal already present; skipping.")
        return

    now = datetime.now(UTC)
    proposal = Proposal(
        id=f"demo-proposal-{uuid.uuid4().hex[:8]}",
        type="policy_tweak",
        summary="Consider enabling memory epochs for shorter sessions.",
        evidence=["Demo evidence point one.", "Demo evidence point two."],
        action={"type": "noop", "reason": "Synthetic demo proposal"},
        confidence=0.85,
        status="pending",
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    await app.proposal_store.save(proposal)
    print(f"Created demo proposal: {proposal.id}")


async def _write_demo_admin_info(user_id: str, path: Path) -> None:
    """Write the demo admin user_id to a small JSON file for helper scripts."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "user_id": user_id,
                "platform": DEMO_PLATFORM,
                "platform_user": DEMO_PLATFORM_USER,
            }
        ),
        encoding="utf-8",
    )


async def main() -> None:
    config_path = Path("config.demo.py")
    if not config_path.exists():
        raise SystemExit(
            "config.demo.py not found. Copy config.demo.example.py to config.demo.py first."
        )

    cfg = HestiaConfig.from_file(config_path)
    app = make_app(cfg)
    await app.bootstrap_db()

    soul_path = cfg.identity.soul_path
    if soul_path is not None:
        await _ensure_soul_file(soul_path)

    user_id = await _ensure_demo_user(app)
    await _ensure_memories(app)
    await _ensure_sample_session(app)
    await _ensure_sample_proposal(app)

    info_path = Path("demo-data") / "demo-admin.json"
    await _write_demo_admin_info(user_id, info_path)

    print("\nDemo instance seeded successfully.")
    print(f"  Dashboard: http://{cfg.web.host}:{cfg.web.port}")
    print(f"  Demo user: {DEMO_PLATFORM_USER}")
    print(f"  Demo admin user_id: {user_id}")
    print("\nAPI login (debug-login endpoint, enabled only by config.demo.py):")
    print(
        f"  curl -s -X POST http://{cfg.web.host}:{cfg.web.port}/api/auth/debug-login "
        f'-H "Content-Type: application/json" -d \'{{"user_id":"{user_id}"}}\''
    )
    print("\nWeb UI login: open the dashboard and select the 'Demo Admin' user.")
    print("              debug_login is enabled, so no 2FA code is required.")


if __name__ == "__main__":
    asyncio.run(main())
