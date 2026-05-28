#!/usr/bin/env python3
"""Warm up a browser session for a site that uses Cloudflare bot protection.

Opens a real headed browser via xvfb-run so it looks like a real user to
Cloudflare, navigates to the site, and waits for the "Managed Challenge" to
auto-resolve. This creates fresh cookies that future headless browser_get calls
can reuse to bypass the challenge — no login required for public sites.

For sites that actually require authentication (e.g. LinkedIn messaging,
Gmail), use the browser_login tool instead.

Usage:
    cd ~/Hestia-runtime
    source .venv/bin/activate
    PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py <domain> [start_url]

Examples:
    PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py indeed.com
    PYTHONPATH=src xvfb-run python3 scripts/warmup_site_session.py ziprecruiter.com
"""

import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Run: uv pip install playwright && playwright install chromium")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from hestia.tools.browser.session_store import BrowserSessionStore

_VIEWPORT = {"width": 1920, "height": 1080}
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


async def warmup_session(domain: str, start_url: str) -> None:
    store = BrowserSessionStore()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport=_VIEWPORT,
            user_agent=_USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()

        # Anti-detection scripts
        await page.add_init_script(
            """
            () => {
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            }
            """
        )

        print(f"Navigating to {start_url} ...")
        await page.goto(start_url, timeout=60000, wait_until="domcontentloaded")

        # Wait for Cloudflare / any challenge to settle
        print("Waiting 15s for challenge/page to settle...")
        await page.wait_for_timeout(15000)

        # Check page state
        text = await page.evaluate("() => document.body.innerText || ''")
        title = await page.title()
        print(f"Page title: {title}")
        if ("Cloudflare" in text or "Verification" in text
                or "security verification" in text.lower()):
            print("WARNING: Cloudflare challenge still present. Waiting another 15s...")
            await page.wait_for_timeout(15000)
            text = await page.evaluate("() => document.body.innerText || ''")
            if "Cloudflare" in text or "Verification" in text:
                print("WARNING: Cloudflare challenge did not auto-resolve.")
            else:
                print("Challenge resolved!")
        else:
            print("Page loaded without challenge.")

        # For job sites, try navigating to a job search to establish deeper cookies
        if "indeed" in domain:
            print("Navigating to Indeed job search...")
            try:
                await page.goto(
                    "https://www.indeed.com/jobs?q=software+engineer&l=remote",
                    timeout=60000,
                    wait_until="domcontentloaded",
                )
                await page.wait_for_timeout(10000)
                text2 = await page.evaluate("() => document.body.innerText || ''")
                if "Cloudflare" not in text2 and "Verification" not in text2:
                    print("Job search page accessible!")
                else:
                    print("Job search still blocked by Cloudflare.")
            except Exception as exc:
                print(f"Job search navigation failed: {exc}")

        elif "ziprecruiter" in domain:
            print("Navigating to ZipRecruiter job search...")
            try:
                await page.goto(
                    "https://www.ziprecruiter.com/jobs?q=software+engineer&l=remote",
                    timeout=60000,
                    wait_until="domcontentloaded",
                )
                await page.wait_for_timeout(10000)
                text2 = await page.evaluate("() => document.body.innerText || ''")
                if "404" not in text2 and "could not be found" not in text2:
                    print("Job search page accessible!")
                else:
                    print("Job search returned 404 — may need different URL.")
            except Exception as exc:
                print(f"Job search navigation failed: {exc}")

        # Save session
        storage = await context.storage_state()
        store.save_storage(domain, storage)
        cookies = await context.cookies()
        store.save_cookies(domain, cookies)

        print(f"Session saved for {domain}. {len(cookies)} cookies stored.")

        await context.close()
        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    domain = sys.argv[1]
    start_url = sys.argv[2] if len(sys.argv) > 2 else f"https://www.{domain}"
    asyncio.run(warmup_session(domain, start_url))
