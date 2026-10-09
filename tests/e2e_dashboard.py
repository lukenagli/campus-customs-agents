"""End-to-end check of the dashboard in headless Edge (backend on :8000, Vite on :5173).

Resets through the UI, runs ticket 102 from the board, approves the rent as
"Luke", confirms cash goes $3,400 -> $1,000, takes screenshots, and resets.

    python tests/e2e_dashboard.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BOARD = "http://localhost:5173"
SHOTS = Path(__file__).resolve().parent.parent / "output" / "screenshots"


def cash(page) -> str:
    return page.get_by_test_id("cash-balance").get_attribute("data-value")


def confirm(page) -> None:
    page.get_by_test_id("confirm-ok").click()


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BOARD)

        print("1. Reset from the UI")
        page.get_by_test_id("reset").click()
        confirm(page)
        expect(page.get_by_test_id("status-102")).to_have_text("Open", timeout=15000)
        expect(page.get_by_test_id("cash-balance")).to_have_attribute("data-value", "3400.00", timeout=15000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOTS / "1_before.png"), full_page=True)
        print("   cash:", cash(page))

        print("2. Run ticket 102 from the board")
        page.get_by_test_id("run-102").click()
        expect(page.get_by_test_id("status-102")).to_have_text("Team working…", timeout=10000)
        page.get_by_test_id("handoff-caption").wait_for(timeout=60000)  # first delegation is visible
        page.wait_for_timeout(700)
        page.screenshot(path=str(SHOTS / "2_during.png"), full_page=True)
        active = [k for k in ("boss", "inventory", "accounting", "facilities", "customer_service")
                  if page.get_by_test_id(f"agent-{k}").get_attribute("data-active") == "true"]
        print("   active agent while running:", active, "|", page.get_by_test_id("handoff-caption").inner_text())

        print("3. Wait for the run to finish")
        expect(page.get_by_test_id("status-102")).to_have_text("Resolved", timeout=240000)
        expect(page.get_by_test_id("ticket-102")).to_contain_text("approval pending")
        page.get_by_test_id("run-summary").wait_for(timeout=20000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOTS / "3_after_run.png"), full_page=True)

        print("4. Approve the rent as Luke")
        approve = page.locator('[data-testid^="approve-"]').first
        expect(approve).to_be_visible(timeout=10000)
        page.get_by_test_id("approver-name").fill("Luke")
        print("   check:", page.locator('[data-testid^="check-"]').first.inner_text().replace("\n", " | ")[:220])
        approve.click()
        expect(page.get_by_test_id("confirm-dialog")).to_contain_text("$3,400.00", timeout=5000)
        confirm(page)
        expect(page.get_by_test_id("cash-balance")).to_have_attribute("data-value", "1000.00", timeout=20000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / "4_paying.png"))  # register mid count-down
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SHOTS / "5_after_approval.png"), full_page=True)
        print("   cash after approval:", cash(page))
        badge_gone = page.get_by_test_id("ticket-102").get_by_text("approval pending").count() == 0
        print("   approval-pending badge cleared:", badge_gone)

        print("5. Narrow window")
        page.set_viewport_size({"width": 420, "height": 900})
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "6_narrow.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})

        print("6. Reset again")
        page.get_by_test_id("reset").click()
        confirm(page)
        expect(page.get_by_test_id("cash-balance")).to_have_attribute("data-value", "3400.00", timeout=15000)
        expect(page.get_by_test_id("status-102")).to_have_text("Open", timeout=15000)
        print("   cash after reset:", cash(page))
        browser.close()

    print("Page errors:", errors or "none")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"Done in {time.time() - t0:.0f}s. Screenshots in {SHOTS}")
