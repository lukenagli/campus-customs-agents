"""Open output/desk_tickets.html in headless Edge and check every tab switches.

Uses the locally installed Microsoft Edge (no browser download):
    pip install playwright
    python tests/check_desk_tickets.py
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = Path(__file__).resolve().parent.parent / "output" / "desk_tickets.html"
TABS = {
    "Ticket 101": ("t101", "Ticket 101: Bulldog tee, size S, qty 1"),
    "Ticket 102": ("t102", "Ticket 102: Rent due"),
    "Ticket 103": ("t103", "Ticket 103: Bulk hoodie discount"),
    "Cash": ("cash", "Cash, itemized"),
    "Reflection": ("reflection", "The run in numbers"),
}
PANELS = [p for p, _ in TABS.values()]


def main() -> None:
    failures, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("request", lambda r: not r.url.startswith("file:") and errors.append(f"external request: {r.url}"))
        page.goto(PAGE.as_uri())

        # Two passes: forward, then in reverse, so every tab is switched to and away from.
        for name in list(TABS) + list(reversed(TABS)):
            panel_id, heading = TABS[name]
            page.get_by_role("tab", name=name).click()
            visible = [pid for pid in PANELS if page.locator(f"#{pid}").is_visible()]
            selected = page.get_by_role("tab", name=name).get_attribute("aria-selected")
            text_ok = heading in page.locator(f"#{panel_id}").inner_text()
            ok = visible == [panel_id] and selected == "true" and text_ok
            print(f"[{'PASS' if ok else 'FAIL'}] {name:10s} -> visible panels {visible}, aria-selected={selected}")
            if not ok:
                failures.append(name)

        flows = {pid: page.locator(f"#{pid} .flow").first.locator(".flow-row").count() for pid in ("t101", "t102", "t103")}  # Expected diagrams
        print("Flow diagram steps rendered:", flows)
        if flows != {"t101": 4, "t102": 3, "t103": 5}:
            failures.append("flow diagrams")

        page.keyboard.press("ArrowRight")  # keyboard nav from the focused tab
        print("Keyboard ArrowRight moved to:", page.locator('[role="tab"][aria-selected="true"]').inner_text())
        page.set_viewport_size({"width": 1100, "height": 1400})
        page.get_by_role("tab", name="Ticket 101").click()
        page.screenshot(path=str(PAGE.with_name("desk_tickets_check.png")), full_page=True)
        browser.close()

    print("Page errors / external requests:", errors or "none")
    if failures or errors:
        sys.exit(f"FAILED: {failures} {errors}")
    print("All tabs switch correctly.")


if __name__ == "__main__":
    main()
