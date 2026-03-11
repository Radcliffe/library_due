#!/usr/bin/env python3
"""
List checked-out library items and due dates from the Ramsey County Library website.

Usage:
    python library_due.py

Optional:
    python library_due.py --json
    python library_due.py --headed
    python library_due.py --debug-html checkedout.html
    python library_due.py --state-file .library_state.json

Installation:
    See README.md. Requires Python 3.9+ and Firefox browser installed.
"""

from __future__ import annotations

import argparse
from enum import Enum, auto
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup
import dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from tabulate import tabulate

dotenv.load_dotenv()

LOGIN_URL = (
    "https://rclreads.bibliocommons.com/user/login"
    "?destination=https%3A%2F%2Frclreads.bibliocommons.com%2Fuser%2Flogin"
    "%3Fdestination%3Duser_dashboard"
)
CHECKED_OUT_URL = "https://rclreads.bibliocommons.com/v2/checkedout/out"
DEFAULT_STATE_FILE = ".library_browser_state.json"
TIMEOUT_MS = 30000

# CSS Selectors
LIST_ITEM_SELECTOR = "div.cp-batch-actions-list-item[data-key='check-out-list-item']"
NAME_INPUT_SELECTOR = "input[name='name']"
PIN_INPUT_SELECTOR = "input[name='user_pin']"
REMEMBER_ME_SELECTOR = "input[name='remember_me']"
WAIT_FOR_SELECTORS = "div.cp-batch-actions-list-item[data-key='check-out-list-item'], .cp-item-list, input[name='name'], input[name='user_pin'], input[name='remember_me']"
TITLE_SELECTOR = "h2.cp-title .title-content"
SUBTITLE_SELECTOR = "h2.cp-title .cp-subtitle"
AUTHOR_SELECTOR = ".cp-by-author-block .author-link"
DUE_DATE_SELECTOR = ".cp-checked-out-due-on .cp-short-formatted-date"
DAYS_REMAINING_SELECTOR = ".cp-due-date-notice .due-date-notice"
RENEW_COUNT_SELECTOR = ".cp-renew-count"
CALL_NUMBER_AND_BARCODE_SELECTOR = ".call-number-and-barcode .cp-item-field"
FIELD_NAME_SELECTOR = ".field-name"
FIELD_VALUE_SELECTOR = ".field-value"

# Field names
CALL_NUMBER_FIELD_NAME = "Call number"
BARCODE_FIELD_NAME = "Barcode"

@dataclass
class CheckedOutItem:
    title: str
    subtitle: Optional[str]
    author: Optional[str]
    due_date: Optional[str]
    days_remaining: Optional[str]
    renew_count: Optional[str]
    call_number: Optional[str]
    barcode: Optional[str]


class PageState(Enum):
    LOGIN_FORM = auto()
    ITEMS_LOADED = auto()
    EMPTY_LIST = auto()
    LOADING = auto()
    UNEXPECTED = auto()


def detect_page_state(page) -> PageState:
    # Check for login form first
    if (
        page.locator(NAME_INPUT_SELECTOR).count() > 0
        and page.locator(PIN_INPUT_SELECTOR).count() > 0
    ):
        return PageState.LOGIN_FORM

    # Check for checked-out items
    if page.locator(LIST_ITEM_SELECTOR).count() > 0:
        return PageState.ITEMS_LOADED

    # Check for empty list container (logged in, nothing out)
    if page.locator(".cp-item-list").count() > 0:
        return PageState.EMPTY_LIST

    # Check if page is still loading (no meaningful content yet)
    if page.locator("body").inner_text().strip() == "":
        return PageState.LOADING

    return PageState.UNEXPECTED


def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def get_field_value(node, selector: str) -> Optional[str]:
    el = node.select_one(selector)
    return clean_text(el.get_text(" ", strip=True)) if el else None


def parse_checked_out_html(html: str) -> List[CheckedOutItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[CheckedOutItem] = []

    for node in soup.select(LIST_ITEM_SELECTOR):
        title = get_field_value(node, TITLE_SELECTOR)
        if not title:
            continue
        subtitle = get_field_value(node, SUBTITLE_SELECTOR)
        author = get_field_value(node, AUTHOR_SELECTOR)
        due_date = get_field_value(node, DUE_DATE_SELECTOR)
        days_remaining = get_field_value(node, DAYS_REMAINING_SELECTOR)
        renew_count = get_field_value(node, RENEW_COUNT_SELECTOR)

        call_number = None
        barcode = None
        for field in node.select(CALL_NUMBER_AND_BARCODE_SELECTOR):
            field_name = get_field_value(field, FIELD_NAME_SELECTOR)
            if field_name not in (CALL_NUMBER_FIELD_NAME, BARCODE_FIELD_NAME):
                continue
            field_value = get_field_value(field, FIELD_VALUE_SELECTOR)
            if not field_value:
                continue
            if field_name == CALL_NUMBER_FIELD_NAME:
                call_number = field_value
            elif field_name == BARCODE_FIELD_NAME:
                barcode = field_value

        items.append(
            CheckedOutItem(
                title=title,
                subtitle=subtitle,
                author=author,
                due_date=due_date,
                days_remaining=days_remaining,
                renew_count=renew_count,
                call_number=call_number,
                barcode=barcode,
            )
        )

    return items


def page_looks_logged_out(page) -> bool:
    try:
        return page.locator(NAME_INPUT_SELECTOR).count() > 0 and page.locator(PIN_INPUT_SELECTOR).count() > 0
    except Exception:
        return False


def perform_login(page, username: str, pin: str, timeout_ms: int) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)

    page.locator(NAME_INPUT_SELECTOR).fill(username)
    page.locator(PIN_INPUT_SELECTOR).fill(pin)

    remember = page.locator(REMEMBER_ME_SELECTOR)
    if remember.count() > 0 and not remember.is_checked():
        remember.check()

    with page.expect_navigation(wait_until="networkidle", timeout=timeout_ms):
        page.locator("input[name='commit']").click()

    if page_looks_logged_out(page):
        raise RuntimeError("Login failed. Check your username/PIN or see if the site changed.")


def login_and_fetch_html(
    username: Optional[str],
    pin: Optional[str],
    state_file: str,
    headed: bool = False,
    timeout_ms: int = TIMEOUT_MS,
) -> str:
    state_path = Path(state_file)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=not headed)

        context_kwargs = {}
        if state_path.exists():
            context_kwargs["storage_state"] = str(state_path)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            page.goto(CHECKED_OUT_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            _wait_for_page(page, timeout_ms)

            state = detect_page_state(page)

            if state == PageState.LOGIN_FORM:
                if not username or not pin:
                    raise RuntimeError(
                        "Saved session is missing or expired, and "
                        "LIBRARY_USERNAME / LIBRARY_PIN were not provided."
                    )
                perform_login(page, username, pin, timeout_ms)
                page.goto(CHECKED_OUT_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                _wait_for_page(page, timeout_ms)
                state = detect_page_state(page)

            if state == PageState.LOGIN_FORM:
                raise RuntimeError(
                    "Still on login page after authentication attempt. "
                    "Check your username/PIN."
                )
            elif state == PageState.ITEMS_LOADED:
                html = page.content()
                context.storage_state(path=str(state_path))
                return html
            elif state == PageState.EMPTY_LIST:
                context.storage_state(path=str(state_path))
                return ""
            elif state == PageState.LOADING:
                raise RuntimeError("Page did not finish loading within timeout.")
            elif state == PageState.UNEXPECTED:
                raise RuntimeError(
                    f"Unexpected page state after navigation. "
                    f"URL: {page.url!r}, title: {page.title()!r}"
                )
            else:
                raise RuntimeError(f"Unhandled page state: {state!r}")

        finally:
            context.close()
            browser.close()


def _wait_for_page(page, timeout_ms: int) -> None:
    """Wait for the page to leave the loading state, without raising on timeout."""
    try:
        page.wait_for_selector(WAIT_FOR_SELECTORS, timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


def print_table(items: List[CheckedOutItem]) -> None:
    if not items:
        print("No checked out items found.")
        return

    rows = []
    for item in items:
        full_title = item.title
        if item.subtitle:
            full_title = f"{full_title}: {item.subtitle}"

        rows.append(
            [
                full_title,
                item.author or "",
                item.due_date or "",
                # item.days_remaining or "",
                item.renew_count or "",
                item.call_number or "",
            ]
        )

    print(
        tabulate(
            rows,
            headers=["Title", "Author", "Due Date", # "Remaining",
                     "Renewals", "Call Number"],
            tablefmt="rounded_grid",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="List checked out library books and due dates.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window for debugging.")
    parser.add_argument("--debug-html", help="Write fetched HTML to this file.")
    parser.add_argument("--input-html", help="Parse from a saved HTML file instead of fetching.")
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help=f"Path to saved browser session state (default: {DEFAULT_STATE_FILE})",
    )
    args = parser.parse_args()

    username = os.environ.get("LIBRARY_USERNAME")
    pin = os.environ.get("LIBRARY_PIN")

    try:
        if args.input_html:
            html = Path(args.input_html).read_text(encoding="utf-8")
        else:
            html = login_and_fetch_html(
                username=username,
                pin=pin,
                state_file=args.state_file,
                headed=args.headed,
            )

            if args.debug_html:
                with open(args.debug_html, "w", encoding="utf-8") as f:
                    f.write(html)

        items = parse_checked_out_html(html)

        if args.json:
            print(json.dumps([asdict(item) for item in items], indent=2))
        else:
            print_table(items)

        return 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
