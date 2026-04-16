#!/usr/bin/env python3
# mypy: disable-error-code="import-untyped"
"""Matrix E2E tester driver — send a message and wait for the bot to reply.

Usage:
    export HESTIA_MATRIX_HOMESERVER=https://matrix.org
    export HESTIA_MATRIX_TESTER_USER_ID=@tester:matrix.org
    export HESTIA_MATRIX_TESTER_ACCESS_TOKEN=syt_...
    export HESTIA_MATRIX_TEST_ROOM_ID='!room:matrix.org'
    export HESTIA_MATRIX_USER_ID=@bot:matrix.org
    python scripts/matrix_test_send.py "ping"

Optional:
    HESTIA_MATRIX_TESTER_DEVICE_ID (default: hestia-e2e-tester)
"""

from __future__ import annotations

import asyncio
import os
import sys
import time


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


async def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <message>", file=sys.stderr)
        return 1

    message = sys.argv[1]

    homeserver = _require_env("HESTIA_MATRIX_HOMESERVER")
    tester_user_id = _require_env("HESTIA_MATRIX_TESTER_USER_ID")
    tester_token = _require_env("HESTIA_MATRIX_TESTER_ACCESS_TOKEN")
    room_id = _require_env("HESTIA_MATRIX_TEST_ROOM_ID")
    bot_mxid = _require_env("HESTIA_MATRIX_USER_ID")
    device_id = os.environ.get("HESTIA_MATRIX_TESTER_DEVICE_ID", "hestia-e2e-tester")

    try:
        from nio import AsyncClient, RoomMessageText, RoomSendResponse, SyncResponse
    except ImportError as exc:
        print(f"matrix-nio not installed: {exc}", file=sys.stderr)
        return 1

    client = AsyncClient(
        homeserver=homeserver,
        user=tester_user_id,
        device_id=device_id,
    )
    client.access_token = tester_token

    start_ts_ms = int(time.time() * 1000)

    try:
        send_resp = await client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": message},
        )
        if not isinstance(send_resp, RoomSendResponse):
            print(f"Failed to send: {send_resp}", file=sys.stderr)
            return 1

        print(f"Sent event {send_resp.event_id}")
        print("Waiting for bot response...")

        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            sync_resp = await client.sync(timeout=3000)
            if isinstance(sync_resp, SyncResponse):
                room_info = sync_resp.rooms.join.get(room_id)
                if room_info:
                    for event in room_info.timeline.events:
                        if (
                            isinstance(event, RoomMessageText)
                            and event.sender == bot_mxid
                            and event.server_timestamp > start_ts_ms
                        ):
                            print(f"Bot reply: {event.body}")
                            return 0
            await asyncio.sleep(0.5)

        print("Timed out waiting for bot response", file=sys.stderr)
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
