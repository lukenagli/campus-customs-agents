"""Test the Problem 5 MCP tools (reads, agent writes, human-only payment) in memory.

Runs against data/campus_customs_new.db and WRITES to it, so it resets the
working copy before and after. The original database is checked unchanged.

Usage (from any folder):
    python tests/test_mcp_write_tools.py
"""

import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp_server"))

from fastmcp import Client  # noqa: E402

from reset_db import ORIGINAL_DB, WORKING_DB, reset_db  # noqa: E402
from server import mcp  # noqa: E402

PASSED, FAILED = [], []


def check(label: str, condition: bool, detail=None) -> None:
    (PASSED if condition else FAILED).append(label)
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if detail is not None:
        print("      ", json.dumps(detail, default=str)[:400])


def db(sql: str, params=()):
    with sqlite3.connect(WORKING_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(sql, params)]
        conn.commit()
    return rows


async def call(client, name, **args):
    return (await client.call_tool(name, args)).structured_content


async def main() -> None:
    original_md5 = hashlib.md5(ORIGINAL_DB.read_bytes()).hexdigest()
    reset_db()

    async with Client(mcp) as c:
        names = sorted(t.name for t in await c.list_tools())
        print("Tools:", ", ".join(names), "\n")

        print("== Read tools")
        r = await call(c, "get_today")
        check("get_today = 2026-08-31", r["date_today"] == "2026-08-31", r)
        r = await call(c, "list_open_tickets")
        check("list_open_tickets returns 101, 102, 103", [t["id"] for t in r["tickets"]] == [101, 102, 103])
        r = await call(c, "get_ticket", ticket_id=103)
        check("get_ticket(103) = 20 x CC-HOOD-NAVY M", r["ticket"]["qty"] == 20 and r["ticket"]["size"] == "M")
        r = await call(c, "get_ticket", ticket_id=999)
        check("get_ticket(999) not found", r["found"] is False, r)
        r = await call(c, "get_pricing", sku="CC-HOOD-NAVY", proposed_price=50.0, qty=20)
        check("get_pricing hoodie at $50 x 20: margin $28, total $1000", r["proposed_margin"] == 28 and r["order_total"] == 1000, r)
        r = await call(c, "get_pricing", sku="CC-HOOD-NAVY", proposed_price=20.0)
        check("get_pricing at $20 flags below_cost", r["below_cost"] is True)
        r = await call(c, "find_vendors", specialty="apparel")
        check("find_vendors('apparel') = Bulldog Print Co, 5 days, blocked",
              [(v["name"], v["lead_days"], v["blocked"]) for v in r["vendors"]] == [("Bulldog Print Co", 5, True)], r)
        r = await call(c, "list_vendors")
        check("list_vendors: 3 vendors, only Bulldog blocked", [v["blocked"] for v in r["vendors"]] == [True, False, False])
        r = await call(c, "get_vendor_open_invoices", vendor_id=1)
        check("get_vendor_open_invoices(1): invoice 501, $840, 3 days overdue",
              r["blocked"] and r["open_invoices"][0]["days_overdue"] == 3 and r["total_open"] == 840, r)
        r = await call(c, "get_cash_balance")
        check("get_cash_balance = 3400, nothing pending", r["checking_balance"] == 3400 and r["pending_payment_total"] == 0, r)
        r = await call(c, "list_obligations")
        check("list_obligations: 501 + rent = 3240, 160 left",
              r["total_owed"] == 3240 and r["cash_after_all"] == 160, r["obligations"])

        print("\n== Agent write tools")
        r = await call(c, "request_purchase_order", ticket_id=103, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12,
                       reason="Ticket 103 shortfall", requested_by="Accounting")
        check("REFUSE: PO to Bulldog Print while invoice 501 is open", r.get("refused") is True, r["error"])
        check("   ...and no request was stored", db("SELECT * FROM approval_requests") == [])
        r = await call(c, "request_payment", ticket_id=102, kind="rent", ref_id=1, amount=2000, reason="Rent", requested_by="Facilities")
        check("REFUSE: rent request with wrong amount", r.get("refused") is True, r["error"])
        r = await call(c, "request_payment", ticket_id=102, kind="rent", ref_id=1, amount=2400,
                       reason="Ticket 102: rent due 2026-09-02", requested_by="Accounting")
        rent_req = r["request_id"]
        check("request_payment rent $2400 -> pending, no money moved",
              r["ok"] and r["money_moved"] is False and db("SELECT balance FROM cash_accounts")[0]["balance"] == 3400, r)
        r = await call(c, "request_payment", ticket_id=102, kind="rent", ref_id=1, amount=2400, reason="again", requested_by="Accounting")
        check("REFUSE: duplicate pending rent request", r.get("refused") is True, r["error"])
        r = await call(c, "request_payment", ticket_id=101, kind="invoice", ref_id=501, amount=840,
                       reason="Ticket 101: overdue invoice blocks restock", requested_by="Accounting")
        inv_req = r["request_id"]
        check("request_payment invoice 501 $840 -> pending; 160 available after pending",
              r["ok"] and r["available_after_pending"] == 160, r)
        r = await call(c, "add_ticket_note", ticket_id=102, author="Boss", note="Rent request sent for approval.")
        check("add_ticket_note on 102", r["ok"], r)
        r = await call(c, "update_ticket_status", ticket_id=102, status="done")
        check("REFUSE: invalid ticket status", r.get("refused") is True, r["error"])
        r = await call(c, "update_ticket_status", ticket_id=102, status="waiting_on_approval")
        check("update_ticket_status 102 -> waiting_on_approval", r["ok"] and r["new_status"] == "waiting_on_approval")
        r = await call(c, "save_customer_draft", ticket_id=101, draft="Hi Tauhid, size S is out of stock...")
        check("save_customer_draft on 101 (not sent)", r["ok"] and r["sent"] is False, r)
        r = await call(c, "get_ticket", ticket_id=101)
        check("get_ticket(101) shows the saved draft", len(r["customer_drafts"]) == 1)

        print("\n== Human-only execute_payment")
        for name in ("Accounting", "Boss agent", "customer_service", "System", ""):
            r = await call(c, "execute_payment", request_id=rent_req, approved_by=name)
            check(f"REFUSE: agent/system name as approved_by ({name!r})", r.get("refused") is True, r["error"])

        db("UPDATE cash_accounts SET balance = 500 WHERE name = 'checking'")  # test fixture
        r = await call(c, "execute_payment", request_id=rent_req, approved_by="Luke Nagli")
        state = db("SELECT (SELECT balance FROM cash_accounts) AS bal, (SELECT next_due FROM leases) AS due, "
                   "(SELECT count(*) FROM payments) AS pays, (SELECT status FROM approval_requests WHERE id = ?) AS st",
                   (rent_req,))[0]
        check("REFUSE: $2400 payment with only $500 cash; nothing changed",
              r.get("refused") is True and state == {"bal": 500, "due": "2026-09-02", "pays": 0, "st": "pending"},
              [r["error"], state])
        db("UPDATE cash_accounts SET balance = 3400 WHERE name = 'checking'")  # restore fixture

        r = await call(c, "execute_payment", request_id=rent_req, approved_by="Luke Nagli")
        check("execute_payment rent by Luke Nagli: 3400 -> 1000, next_due -> 2026-10-02",
              r["ok"] and r["new_balance"] == 1000 and r["new_next_due"] == "2026-10-02", r)
        check("   ...payments row written",
              db("SELECT kind, ref_id, amount, account, paid_at, approved_by FROM payments") ==
              [{"kind": "rent", "ref_id": 1, "amount": 2400.0, "account": "checking",
                "paid_at": "2026-08-31", "approved_by": "Luke Nagli"}])
        r = await call(c, "execute_payment", request_id=rent_req, approved_by="Luke Nagli")
        check("REFUSE: executing the same request twice", r.get("refused") is True, r["error"])

        r = await call(c, "execute_payment", request_id=inv_req, approved_by="Luke Nagli")
        check("execute_payment invoice 501: 1000 -> 160, invoice paid",
              r["ok"] and r["new_balance"] == 160 and r["invoice_status"] == "paid", r)
        r = await call(c, "request_purchase_order", ticket_id=103, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12,
                       reason="Ticket 103 shortfall", requested_by="Accounting")
        check("REFUSE: 12-hoodie PO ($264) with only $160 cash", r.get("refused") is True, r["error"])
        r = await call(c, "request_purchase_order", ticket_id=101, vendor_id=1, sku="CC-TEE-WHITE", size="S", qty=1,
                       reason="Ticket 101 restock", requested_by="Inventory")
        po_req = r["request_id"]
        check("PO to Bulldog after 501 is paid: 1 tee, $8, arrives 2026-09-05",
              r["ok"] and r["amount"] == 8 and r["expected_arrival_if_approved_today"] == "2026-09-05", r)
        r = await call(c, "execute_payment", request_id=po_req, approved_by="Luke")
        stock = db("SELECT qty FROM inventory WHERE sku = 'CC-TEE-WHITE' AND size = 'S'")[0]["qty"]
        check("execute_payment on the PO: 160 -> 152, stock NOT added (still 0)",
              r["ok"] and r["new_balance"] == 152 and r["kind"] == "purchase_order" and stock == 0, r)
        check("   ...approval notes added to tickets 102 and 101",
              len(db("SELECT * FROM ticket_notes WHERE author = 'Luke Nagli' AND ticket_id = 102")) == 1
              and len(db("SELECT * FROM ticket_notes WHERE author = 'Luke' AND ticket_id = 101")) == 1)
        check("   ...every approval request has a ticket_id",
              db("SELECT count(*) AS n FROM approval_requests WHERE ticket_id IS NULL")[0]["n"] == 0)
        r = await call(c, "request_purchase_order", ticket_id=103, vendor_id=1, sku="CC-HOOD-NAVY", size="M",
                       qty=1, reason="test", requested_by="Accounting")
        r = await call(c, "reject_request", request_id=r["request_id"], rejected_by="Luke", reason="test")
        check("reject_request on a PO: no money moved",
              r["ok"] and r["money_moved"] is False and db("SELECT balance FROM cash_accounts")[0]["balance"] == 152, r)
        r = await call(c, "list_payments")
        check("list_payments: 3 payments, $3,248 total, balance 152",
              r["count"] == 3 and r["total_paid"] == 3248 and r["checking_balance"] == 152, r)

    reset_db()
    check("Original DB unchanged", hashlib.md5(ORIGINAL_DB.read_bytes()).hexdigest() == original_md5)
    check("Working copy reset to match original",
          hashlib.md5(WORKING_DB.read_bytes()).hexdigest() == original_md5)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
