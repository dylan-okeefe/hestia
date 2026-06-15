#!/usr/bin/env python3
"""Test the job email workflow against a specific email from the inbox.

Usage:
    cd /home/<user>/Hestia-runtime
    . .venv/bin/activate
    EMAIL_APP_PASSWORD=... PYTHONPATH=src python scripts/test_workflow_email.py [UID]

If no UID is provided, lists recent emails with their UIDs.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hestia.app import make_app
from hestia.config import HestiaConfig
from hestia.email.adapter import EmailAdapter
from hestia.workflows.executor import WorkflowExecutor
from hestia.workflows.store import WorkflowStore


async def list_emails(adapter: EmailAdapter, count: int = 20):
    """List recent emails with their UIDs."""
    async with adapter.imap_session() as conn:
        conn.select("INBOX")
        _, data = conn.search(None, "ALL")
        uids = data[0].split()
        print(f"Total emails in inbox: {len(uids)}")
        print()

        for uid in uids[-count:]:
            _, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    header = response_part[1].decode()
                    # Extract subject
                    subject = ""
                    from_addr = ""
                    for line in header.split("\n"):
                        if line.startswith("Subject:"):
                            subject = line.replace("Subject:", "").strip()[:70]
                        elif line.startswith("From:"):
                            from_addr = line.replace("From:", "").strip()[:40]
                    print(f"  UID {uid.decode():>3} | {from_addr:<40} | {subject}")


async def read_email(adapter: EmailAdapter, uid: str) -> dict:
    """Read a specific email by UID.

    The inbox contains forwarded emails from user@example.com.
    The original sender/subject are in the body as HESTIA-META headers.
    """
    result = await adapter.read_message(uid)
    headers = result.get("headers", {})
    body = result.get("body", "")

    # Forwarded emails have the original info in the body
    from_addr = ""
    subject = ""
    if "Original-From:" in body:
        for line in body.split("\n")[:10]:
            if line.startswith("Original-From:"):
                from_addr = line.replace("Original-From:", "").strip()
            elif line.startswith("Original-Subject:"):
                subject = line.replace("Original-Subject:", "").strip()
            elif line.startswith("Subject:") and not subject:
                # Some forwards use Subject: directly
                subject = line.replace("Subject:", "").strip()

    # Fallback to IMAP headers if body parsing failed
    if not from_addr:
        from_addr = headers.get("from", "")
    if not subject:
        subject = headers.get("subject", "")

    return {
        "from_address": from_addr,
        "subject": subject,
        "body": body,
    }


async def run_workflow(payload: dict):
    """Run the active job_email_processor workflow with the given payload."""
    app = make_app(config_path=Path("config.runtime.py"))
    await app.bootstrap_db()

    store = WorkflowStore(app.db)
    workflow = await store.get_workflow("8a86ca59-34bc-4655-b6e3-baabda8b0ebb")
    version = await store.get_active_version(workflow.id)

    executor = WorkflowExecutor(app)
    result = await executor.execute(
        workflow.id,
        trigger_payload=payload,
        version_id=str(version.version),
    )

    await app.close()
    return result


def print_result(result):
    """Pretty-print workflow execution result."""
    print()
    print("=" * 60)
    print(f"Status: {result.status}")
    print(f"Elapsed: {result.total_elapsed_ms}ms")
    print(f"Tokens: {result.total_prompt_tokens} prompt / "
          f"{result.total_completion_tokens} completion")
    print("=" * 60)
    for nr in result.node_results:
        print()
        print(f"  [{nr.status}] {nr.node_id} ({nr.elapsed_ms}ms)")
        output = nr.output
        if isinstance(output, str):
            if len(output) > 500:
                output = output[:500] + "\n  ... [truncated]"
            print(f"  → {output}")
        elif output is not None:
            print(f"  → {json.dumps(output, indent=2, default=str)[:500]}")
        if nr.error:
            print(f"  ✗ ERROR: {nr.error}")


async def main():
    cfg = HestiaConfig.from_file(Path("config.runtime.py"))
    adapter = EmailAdapter(cfg.email)

    if len(sys.argv) < 2:
        print("Recent emails in inbox:")
        print()
        await list_emails(adapter, count=30)
        print()
        print("Usage: python test_workflow_email.py <UID>")
        print("       python test_workflow_email.py --all   # run all unread emails")
        return

    arg = sys.argv[1]

    if arg == "--all":
        # Process all unread emails one by one
        async with adapter.imap_session() as conn:
            conn.select("INBOX")
            _, data = conn.search(None, "UNSEEN")
            uids = data[0].split()
            print(f"Processing {len(uids)} unread emails...")
            for uid in uids:
                email = await read_email(adapter, uid.decode())
                payload = {
                    "from_address": email.get("from_address", ""),
                    "subject": email.get("subject", ""),
                    "body": email.get("body", ""),
                }
                print(f"\n--- UID {uid.decode()}: {payload['subject'][:60]} ---")
                result = await run_workflow(payload)
                print_result(result)
        return

    # Single email test
    uid = arg
    print(f"Reading email UID {uid}...")
    email = await read_email(adapter, uid)

    payload = {
        "from_address": email.get("from_address", ""),
        "subject": email.get("subject", ""),
        "body": email.get("body", ""),
    }

    print(f"Subject: {payload['subject'][:80]}")
    print(f"From: {payload['from_address'][:60]}")

    result = await run_workflow(payload)
    print_result(result)


if __name__ == "__main__":
    asyncio.run(main())
