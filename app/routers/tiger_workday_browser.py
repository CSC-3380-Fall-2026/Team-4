"""Open LSU Workday in a Chromium window and read the grids of three pages.

Playwright is only installed when the app runs locally, so it is imported
inside read_workday and the app starts without it.
"""

import importlib.util
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models.tiger_session import Session
from models.tiger_workday import WorkdayStatus

if TYPE_CHECKING:
    from playwright.sync_api import Page

PROFILE_DIR: Path = Path.home() / ".tiger_workday"
LSU_WORKDAY: str = "https://www.myworkday.com/lsu"
COURSES_TASK: str = "/d/task/2998$28771.htmld#backheader=true"
LOGIN_MS: int = 10 * 60_000
EXTRACT_JS: str = (
    Path(__file__).parent.parent / "static" / "js" / "workday-extract.js"
).read_text(encoding="utf-8")
GRID_ROW: str = 'table[data-automation-id="table"] tbody tr'
HEADER_TITLE: str = '[data-automation-id="pageHeaderTitleText"]'
SYNCED_KEY: str = "workday_synced_at"


class WorkdayError(Exception):
    """A sync that could not finish, with a message safe to show the student."""


def workday_ready() -> bool:
    """Tell whether this server can open a Workday window.

    Returns:
        False on Vercel or when Playwright is not installed.
    """
    return not os.getenv("VERCEL") and importlib.util.find_spec("playwright") is not None


def sync_status(session: Session) -> WorkdayStatus:
    """Say whether Workday sync is available here and when the student last ran it.

    Args:
        session: The verified student; the last sync time is in its metadata.

    Returns:
        Availability, whether the student has synced, and when.
    """
    stamp = session.meta.get(SYNCED_KEY)
    return WorkdayStatus(available=workday_ready(), connected=bool(stamp), last_sync=stamp)


def settle(page: "Page") -> None:
    """Wait until a Workday page has drawn its grids.

    Args:
        page: The Workday tab.
    """
    from playwright.sync_api import TimeoutError as PageTimeout

    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PageTimeout:
        pass
    page.wait_for_selector(GRID_ROW, timeout=60_000)
    page.wait_for_timeout(1000)


def open_nav(page: "Page", label: str) -> None:
    """Open one page under the "Academic History" menu.

    Args:
        page: The Workday tab.
        label: Menu entry, such as "My Academic Record".
    """
    item = '[data-automation-id="navigationItem"][aria-label="{}"]'
    history = page.locator(item.format("Academic History")).first
    if history.get_attribute("aria-expanded") != "true":
        history.click()
    old = page.locator(HEADER_TITLE).first.inner_text()
    page.locator(item.format(label)).first.click()
    page.wait_for_function(
        f"old => document.querySelector('{HEADER_TITLE}')?.innerText !== old",
        arg=old,
        timeout=20_000,
    )
    settle(page)


def scrape(page: "Page") -> list[dict[str, Any]]:
    """Read every grid on the page, clicking through paginated ones.

    Args:
        page: The Workday tab.

    Returns:
        The grids as workday-extract.js returns them.
    """
    tables = page.evaluate(EXTRACT_JS)
    buttons = page.get_by_role("button", name=re.compile(r"^next( page)?$", re.I))
    for _ in range(30):
        ready = [
            button
            for button in buttons.all()
            if button.is_visible()
            and button.is_enabled()
            and button.get_attribute("aria-disabled") != "true"
        ]
        if not ready:
            break
        ready[0].click()
        page.wait_for_timeout(1500)
        for table, more in zip(tables, page.evaluate(EXTRACT_JS)):
            table["rows"] += [row for row in more["rows"] if row not in table["rows"]]
    return tables


def read_pages(page: "Page", workday: str) -> dict[str, Any]:
    """Wait for the student to sign in, then read the three Workday pages.

    Args:
        page: A fresh tab.
        workday: Workday base URL, such as "https://www.myworkday.com/lsu".

    Returns:
        {"courses": [...], "record": [...], "progress": [...]} grids.

    Raises:
        WorkdayError: When the student does not sign in within LOGIN_MS.
    """
    from playwright.sync_api import TimeoutError as PageTimeout

    page.goto(workday + COURSES_TASK)
    if not page.url.startswith(workday):
        try:
            page.wait_for_url(f"{workday}**", timeout=LOGIN_MS)
        except PageTimeout as error:
            raise WorkdayError(
                "Workday sign-in timed out. Please try again."
            ) from error
        page.goto(workday + COURSES_TASK)
    settle(page)
    courses = scrape(page)
    open_nav(page, "My Academic Record")
    record = scrape(page)
    open_nav(page, "My Academic Progress")
    return {"courses": courses, "record": record, "progress": scrape(page)}


def read_workday() -> dict[str, Any]:
    """Open a Chromium window on Workday and read the student's pages.

    The student signs in and does Duo in the window; it closes when done.
    Login cookies stay in ~/.tiger_workday, so later syncs may skip sign-in.

    Returns:
        The raw grids of the three pages, also saved to
        ~/.tiger_workday/last_sync.json.

    Raises:
        WorkdayError: When the window is closed, sign-in times out, or
            Workday does not load.
    """
    from playwright.sync_api import Error as PageError
    from playwright.sync_api import TimeoutError as PageTimeout
    from playwright.sync_api import sync_playwright

    workday = os.getenv("WORKDAY_URL", LSU_WORKDAY).rstrip("/")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as driver:
            # Only the end-to-end test hides the window.
            context = driver.chromium.launch_persistent_context(
                str(PROFILE_DIR / "browser"),
                headless=os.getenv("WORKDAY_HEADLESS") == "1",
            )
            try:
                tab = context.pages[0] if context.pages else context.new_page()
                raw = read_pages(tab, workday)
            finally:
                context.close()
    except PageTimeout as error:
        raise WorkdayError("Workday took too long to load. Please try again.") from error
    except PageError as error:
        if "closed" in str(error):
            raise WorkdayError(
                "The Workday window was closed before the sync finished."
            ) from error
        raise WorkdayError(f"Chromium could not open Workday: {str(error).splitlines()[0]}") from error
    (PROFILE_DIR / "last_sync.json").write_text(json.dumps(raw), encoding="utf-8")
    return raw
