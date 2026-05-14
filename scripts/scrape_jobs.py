#!/usr/bin/env python3
"""Standalone job scraper for Dylan O'Keefe.

Usage: python scripts/scrape_jobs.py [--output FILE]
"""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from curl_cffi.requests import AsyncSession


@dataclass
class Job:
    """A scraped job listing."""

    title: str
    company: str
    location: str
    salary: str
    posted: str
    level: str
    source: str


SENIOR_KEYWORDS = ("senior", "staff", "principal", "lead")
EXCLUDE_KEYWORDS = ("junior", "jr.", "jr ", "mid", "entry", "intern", "internship")


def _is_senior(title: str, level: str = "") -> bool:
    """Return True if the job appears to be senior-level."""
    combined = f"{title} {level}".lower()
    if any(kw in combined for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in combined for kw in SENIOR_KEYWORDS)


def _clean_html(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())


async def _fetch_builtin_boston(session: AsyncSession, page: int) -> str:  # type: ignore[type-arg]
    """Fetch a page of Built In Boston search results."""
    url = (
        "https://www.builtinboston.com/jobs/remote/dev-engineering"
        f"?search=react&page={page}"
    )
    response = await session.get(url, timeout=15)
    response.raise_for_status()
    return str(response.text)


def _parse_builtin_boston(html: str) -> list[Job]:
    """Parse job listings from Built In Boston HTML."""
    jobs: list[Job] = []
    job_ids = sorted(
        set(re.findall(r'data-builtin-track-job-id="(\d+)"', html))
    )

    for job_id in job_ids:
        idx = html.find(f'data-builtin-track-job-id="{job_id}"')
        if idx == -1:
            continue
        chunk = html[idx : idx + 3500]

        company_match = re.search(
            r'data-id="company-title"[^>]*>.*?<span>([^<]+)</span>', chunk
        )
        title_match = re.search(
            r'class="card-alias-after-overlay[^"]*"[^>]*>([^<]+)</a>', chunk
        )
        posted_match = re.search(
            r'fa-regular fa-clock[^"]*"></i>([^<]+)</span>', chunk
        )

        # Extract all font-barlow text-gray-04 spans in order
        spans = re.findall(
            r'<span[^>]*class="font-barlow text-gray-04"[^>]*>([^<]+)</span>',
            chunk,
        )

        work_type = ""
        location = ""
        salary = ""
        level = ""
        for span in spans:
            span = span.strip()
            if span in ("Remote or Hybrid", "In-Office or Remote", "Remote"):
                work_type = span
            elif not location and not span.endswith(" Annually") and "level" not in span.lower():
                location = span
            elif " Annually" in span:
                salary = span
            elif "level" in span.lower() or "expert" in span.lower():
                level = span

        # Some cards omit location but keep work type
        if not location and work_type:
            location = work_type

        if not title_match or not company_match:
            continue

        title = _clean_html(title_match.group(1))
        company = _clean_html(company_match.group(1))
        posted = _clean_html(posted_match.group(1)) if posted_match else ""

        # Build detail URL from schema.org data or construct it
        url_match = re.search(
            r'href="(/job/[^"]+/' + re.escape(job_id) + r')"', chunk
        )
        source = (
            f"https://www.builtinboston.com{url_match.group(1)}"
            if url_match
            else "https://www.builtinboston.com"
        )

        jobs.append(
            Job(
                title=title,
                company=company,
                location=location,
                salary=salary,
                posted=posted,
                level=level,
                source=source,
            )
        )

    return jobs


async def _fetch_reactjobs(session: AsyncSession) -> str:  # type: ignore[type-arg]
    """Fetch ReactJobs.io remote listings."""
    url = "https://reactjobs.io/jobs/reactjs/remote"
    response = await session.get(url, timeout=15)
    response.raise_for_status()
    return str(response.text)


def _parse_reactjobs(html: str) -> list[Job]:
    """Parse job listings from ReactJobs.io HTML."""
    jobs: list[Job] = []
    list_items = re.findall(r"<li[^>]*>(.*?)</li>", html, re.S)
    job_items = [li for li in list_items if "Company" in li]

    for item in job_items:
        fields = dict(
            re.findall(
                r'<dt class="sr-only">([^<]+)</dt>\s*<dd[^>]*>(.*?)</dd>',
                item,
                re.S,
            )
        )

        company = _clean_html(fields.get("Company", ""))
        title = _clean_html(fields.get("Title", ""))
        location = _clean_html(fields.get("Location", ""))
        employment = _clean_html(fields.get("Employment Type", ""))
        posted = _clean_html(fields.get("Posted", ""))

        url_match = re.search(
            r'href="(https://reactjobs\.io/react-jobs/[^"]+)"', item
        )
        source = url_match.group(1) if url_match else "https://reactjobs.io"

        if not title or not company:
            continue

        jobs.append(
            Job(
                title=title,
                company=company,
                location=location,
                salary=employment,
                posted=posted,
                level="",
                source=source,
            )
        )

    return jobs


def _filter_jobs(jobs: list[Job]) -> list[Job]:
    """Keep only senior-level jobs."""
    return [j for j in jobs if _is_senior(j.title, j.level)]


def _deduplicate(jobs: list[Job]) -> list[Job]:
    """Remove duplicate listings by company + title."""
    seen: set[tuple[str, str]] = set()
    result: list[Job] = []
    for j in jobs:
        key = (j.company.lower(), j.title.lower())
        if key not in seen:
            seen.add(key)
            result.append(j)
    return result


def _render_markdown(jobs: list[Job]) -> str:
    """Render jobs to Markdown matching the existing output format."""
    lines = [
        "# Remote Software Development Jobs",
        "",
        "*Generated for Dylan O'Keefe — Senior Front-End Engineer*",
        f"*Date: {datetime.now().strftime('%B %d, %Y')}*",
        "",
        "---",
        "",
        "## Job Listings",
        "",
    ]

    for i, job in enumerate(jobs, start=1):
        lines.append(f"### {i}. {job.title} — {job.company}")
        lines.append(f"- **Company:** {job.company}")
        lines.append(f"- **Title:** {job.title}")
        lines.append(f"- **Location:** {job.location or 'Remote'}")
        if job.salary:
            lines.append(f"- **Salary:** {job.salary}")
        lines.append(f"- **Posted:** {job.posted}")
        if job.level:
            lines.append(f"- **Level:** {job.level}")
        lines.append(f"- **Source:** {job.source}")
        lines.append("")

    return "\n".join(lines)


async def main() -> None:
    """Run the scraper and write output."""
    parser = argparse.ArgumentParser(
        description="Scrape remote React/frontend senior jobs."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/home/dylan/Documents/Job Search/remote_software_development_jobs.md"),
        help="Output Markdown file path",
    )
    args = parser.parse_args()

    all_jobs: list[Job] = []

    async with AsyncSession(impersonate="chrome") as session:
        # Built In Boston — pages 1-3
        for page in range(1, 4):
            html = await _fetch_builtin_boston(session, page)
            jobs = _parse_builtin_boston(html)
            all_jobs.extend(jobs)
            # Stop early if page looks empty
            if not jobs:
                break

        # ReactJobs.io
        html = await _fetch_reactjobs(session)
        all_jobs.extend(_parse_reactjobs(html))

    filtered = _filter_jobs(all_jobs)
    deduped = _deduplicate(filtered)
    markdown = _render_markdown(deduped)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"Scraped {len(deduped)} jobs → {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
