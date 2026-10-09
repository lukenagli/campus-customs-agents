"""Screenshot the live board (each resolved ticket + the cash display) into one self-contained page.

Needs the backend on :8000 and the board on :5173. Only clicks ticket slips
(read-only); never runs, approves, or resets anything.

    python scripts/build_resolved_board.py
"""

import base64
import html
import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "resolved_board.html"
RESOLVED = json.loads((ROOT / "output" / "resolved_tickets.json").read_text(encoding="utf-8"))
BOARD = "http://localhost:5173"


def b64(png: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(png).decode()


def main() -> None:
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(BOARD)
        expect(page.get_by_test_id("cash-balance")).to_have_attribute("data-value", "160.00", timeout=15000)
        for t in RESOLVED["tickets"]:
            tid = t["id"]
            expect(page.get_by_test_id(f"status-{tid}")).to_have_text("Resolved", timeout=10000)
            page.get_by_test_id(f"ticket-{tid}").click()
            summary = page.get_by_test_id("run-summary")
            expect(summary).to_contain_text(f"ticket #{tid}", timeout=15000)
            page.wait_for_timeout(2800)  # let the stamp / desk replay settle
            img = page.screenshot(full_page=True, type="jpeg", quality=72)
            approvals = "; ".join(f"request #{a['request_id']} {a['kind']} ${a['amount']:,.2f} {a['decision']} by {a['approved_by']}"
                                  for a in t["human_approvals"]) or "no approvals needed"
            agents = ", ".join(a["agent"] for a in t["agents"])
            shots.append((f"Ticket {tid}: {t['subject']} ({t['requester']})",
                          f"Status <b>{t['final_status']}</b>. {html.escape(t['outcome'])} Agents: {agents}. "
                          f"Human approvals: {html.escape(approvals)}. The shift report at the bottom shows each "
                          "agent's summary, tools, and handoffs.", b64(img)))
            print(f"ticket {tid}: {len(img) // 1024} KB")
        cash = page.locator(".area-side").screenshot(type="jpeg", quality=85)
        bal = RESOLVED["checking_balance"]
        shots.append(("Cash register", f"Checking at <b>${bal:,.2f}</b> after the run, with nothing pending. The "
                      "receipt tape lists both payments signed by Luke: rent $2,400.00 (ticket 102) and invoice 501 "
                      "$840.00 (ticket 101). $3,400.00 − $3,240.00 = $160.00 (see the Cash tab in desk_tickets.html).",
                      b64(cash)))
        print(f"cash: {len(cash) // 1024} KB")
        browser.close()

    figures = "\n".join(
        f'''  <figure>
    <h2>{html.escape(title)}</h2>
    <img src="{src}" alt="{html.escape(title)}">
    <figcaption>{caption}</figcaption>
  </figure>''' for title, caption, src in shots)
    OUT.write_text(f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs: Resolved Board</title>
<style>
  body {{ margin: 0; font: 15px/1.55 "Segoe UI", system-ui, sans-serif; color: #1d2433; background: #ece2cd; }}
  header {{ background: #00356b; color: #fff; padding: 20px 28px; border-bottom: 4px solid #c99a2e; }}
  header h1 {{ margin: 0; font: 700 22px Georgia, serif; }} header p {{ margin: 4px 0 0; color: #c8d6ea; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 24px 20px 48px; display: grid; gap: 28px; }}
  figure {{ margin: 0; background: #fffaf0; border: 1px solid #ddd0b6; border-radius: 12px; padding: 16px 18px;
           box-shadow: 0 6px 18px rgba(40,30,10,.1); }}
  figure h2 {{ margin: 0 0 10px; font-size: 17px; color: #00356b; }}
  figure img {{ display: block; max-width: 100%; height: auto; border: 1px solid #ddd0b6; border-radius: 6px; }}
  figcaption {{ margin-top: 10px; font-size: 14px; color: #3b4252; }}
</style>
</head>
<body>
<header>
  <h1>Campus Customs: the resolved board</h1>
  <p>Screenshots of the live dashboard after the final run (tickets 102 → 101 → 103, approvals signed by Luke).
     Images are embedded, so this file works on its own.</p>
</header>
<main>
{figures}
</main>
</body>
</html>
''', encoding="utf-8")
    print(f"wrote {OUT.name}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
