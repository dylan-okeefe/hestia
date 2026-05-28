"""Tools for the job alert workflow queue."""

from __future__ import annotations

from typing import Any

from hestia.persistence.job_alert_store import JobAlertStore
from hestia.tools.capabilities import MEMORY_READ, MEMORY_WRITE
from hestia.tools.metadata import tool


def make_save_job_alert_tool(store: JobAlertStore) -> Any:
    """Create a save_job_alert tool bound to a JobAlertStore."""

    @tool(
        name="save_job_alert",
        public_description=(
            "Save a rated job alert to the daily digest queue. "
            "Params: source_email, subject, title, company, location, "
            "remote, match_score, salary, tech_stack, url, summary."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "source_email": {"type": "string", "description": "Sender email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "title": {"type": "string", "description": "Job title."},
                "company": {"type": "string", "description": "Company name."},
                "location": {"type": "string", "description": "Job location."},
                "remote": {
                    "type": "string",
                    "description": "Remote status: Yes, No, Hybrid, or Unknown.",
                },
                "match_score": {"type": "integer", "description": "Match score 1-10."},
                "salary": {"type": "string", "description": "Salary range or Unknown."},
                "tech_stack": {"type": "string", "description": "Key technologies."},
                "url": {"type": "string", "description": "Job listing URL."},
                "summary": {"type": "string", "description": "One-line summary of the job."},
            },
            "required": ["source_email", "subject"],
        },
        tags=["workflow", "builtin"],
        capabilities=[MEMORY_WRITE],
    )
    async def save_job_alert(
        source_email: str = "",
        subject: str = "",
        title: str = "",
        company: str = "",
        location: str = "",
        remote: str = "",
        match_score: int = 0,
        salary: str = "",
        tech_stack: str = "",
        url: str = "",
        summary: str = "",
    ) -> str:
        """Save a job alert to the queue for the daily digest."""
        alert_id = await store.save_alert(
            source_email=source_email,
            subject=subject,
            title=title,
            company=company,
            location=location,
            remote=remote,
            match_score=match_score or None,
            salary=salary,
            tech_stack=tech_stack,
            url=url,
            summary=summary,
        )
        return f"Saved job alert {alert_id}: {title or subject}"

    return save_job_alert


def make_list_pending_alerts_tool(store: JobAlertStore) -> Any:
    """Create a list_pending_alerts tool bound to a JobAlertStore."""

    @tool(
        name="list_pending_alerts",
        public_description=(
            "List unsent job alerts in the daily digest queue. "
            "Params: limit (int, default 50)."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max alerts to return (default 50)."},
            },
        },
        tags=["workflow", "builtin"],
        capabilities=[MEMORY_READ],
    )
    async def list_pending_alerts(limit: int = 50) -> str:
        """Return pending job alerts formatted for a digest."""
        alerts = await store.list_pending(limit=limit)
        if not alerts:
            return "No pending job alerts."

        lines = []
        for a in alerts:
            score = f"Match: {a['match_score']}/10" if a.get("match_score") else "Match: N/A"
            remote = f" | Remote: {a['remote']}" if a.get("remote") else ""
            loc = f" | Location: {a['location']}" if a.get("location") else ""
            salary = f" | Salary: {a['salary']}" if a.get("salary") else ""
            tech = f" | Tech: {a['tech_stack']}" if a.get("tech_stack") else ""
            url = f" | URL: {a['url']}" if a.get("url") else ""
            title = a.get("title") or a["subject"]
            company = f" at {a['company']}" if a.get("company") else ""
            lines.append(f"- {title}{company} | {score}{remote}{loc}{salary}{tech}{url}")
            if a.get("summary"):
                lines.append(f"  {a['summary']}")
        return "\n".join(lines)

    return list_pending_alerts


def make_mark_alerts_sent_tool(store: JobAlertStore) -> Any:
    """Create a mark_alerts_sent tool bound to a JobAlertStore."""

    @tool(
        name="mark_alerts_sent",
        public_description="Mark all pending job alerts as sent in the digest queue.",
        parameters_schema={"type": "object", "properties": {}},
        tags=["workflow", "builtin"],
        capabilities=[MEMORY_WRITE],
    )
    async def mark_alerts_sent() -> str:
        """Mark all pending alerts as sent."""
        count = await store.mark_all_sent()
        return f"Marked {count} job alert(s) as sent."

    return mark_alerts_sent
