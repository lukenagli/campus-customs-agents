"""Campus Customs MCP server.

Tools over the shop's working database (data/campus_customs_new.db). The
original data/campus_customs.db is never opened. "Today" always comes from
desk.date_today, never the system clock.

Tool groups:
- Read tools: never change anything (SQLite read-only connections).
- Agent write tools: ticket notes, ticket status, customer drafts, and
  *pending* payment / purchase-order requests. None of them move money or
  contact anyone.
- Human-only tools: execute_payment and reject_request. Only the backend's
  human-approval step calls these; no agent is ever given them.

The server adds three tables to the working copy on first write
(approval_requests, ticket_notes, customer_drafts). reset_db.py clears them.

Run:
    python mcp_server/server.py
"""

import re
import sqlite3
from calendar import monthrange
from contextlib import closing
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

# Built from this file's location so the server works from any folder.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
AGENT_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
HUMAN_ONLY = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer service"}
# Words that mark a non-human approver (checked as whole words).
NON_HUMAN_WORDS = AGENT_NAMES | {"agent", "bot", "ai", "assistant", "system", "auto", "automation", "llm", "model"}

TICKET_STATUSES = ("open", "in_progress", "waiting_on_approval", "waiting_on_restock", "resolved")
PAYMENT_KINDS = ("invoice", "rent")
REQUEST_KINDS = PAYMENT_KINDS + ("purchase_order",)
CASH_ACCOUNT = "checking"
MAX_TEXT = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,        -- tickets.id the request belongs to
    kind TEXT NOT NULL,                -- invoice | rent | purchase_order
    ref_id INTEGER,                    -- invoices.id / leases.id / vendors.id
    amount REAL NOT NULL,              -- payment amount, or PO cost (qty x unit_cost)
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | executed | rejected
    created_on TEXT NOT NULL,          -- desk.date_today
    vendor_id INTEGER,
    sku TEXT,
    size TEXT,
    qty INTEGER,
    decided_by TEXT,
    decided_on TEXT,
    payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS ticket_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    note TEXT NOT NULL,
    created_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    draft TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft_not_sent',
    created_on TEXT NOT NULL
);
"""

mcp = FastMCP(
    name="Campus Customs",
    instructions=(
        "Tools for the Campus Customs shop database. All dates are judged against "
        "desk.date_today (the shop's 'today'), never the real date. Agents may read data, "
        "add ticket notes, set ticket status, save customer drafts (never sent), and create "
        "PENDING payment or purchase-order requests. Only a human can execute a payment."
    ),
)


# ---------------------------------------------------------------- helpers

def _check_db() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. Run `python reset_db.py` to create it."
        )


def _connect() -> sqlite3.Connection:
    """Open the working database read-only. Refuses to create a missing file."""
    _check_db()
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_rw() -> sqlite3.Connection:
    """Open the working database for writing and make sure the board tables exist."""
    _check_db()
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=rw", uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _today(conn: sqlite3.Connection) -> date:
    """The shop's 'today' from desk.date_today."""
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise ValueError("desk table has no date_today row.")
    return date.fromisoformat(row["date_today"])


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _not_found(message: str) -> dict:
    return {"found": False, "error": message}


def _refuse(message: str, **extra) -> dict:
    return {"ok": False, "refused": True, "error": message, **extra}


def _clean_text(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{field} cannot be empty.")
    if len(value) > MAX_TEXT:
        raise ValueError(f"{field} is longer than {MAX_TEXT} characters.")
    return value


def _is_human_name(name: str) -> bool:
    """A human approver: a real-looking name that isn't an agent or system label."""
    cleaned = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,79}", cleaned):
        return False
    words = re.sub(r"[_\-.]", " ", cleaned.lower()).split()
    if " ".join(words) in AGENT_NAMES or any(w in NON_HUMAN_WORDS for w in words):
        return False
    return "customerservice" not in "".join(words)


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def _open_invoices(conn: sqlite3.Connection, today: date, vendor_id: int | None = None) -> list[dict]:
    sql = """
        SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date, i.description
        FROM invoices AS i LEFT JOIN vendors AS v ON v.id = i.vendor_id
        WHERE i.status = 'open'
    """
    params: tuple = ()
    if vendor_id is not None:
        sql += " AND i.vendor_id = ?"
        params = (vendor_id,)
    rows = conn.execute(sql + " ORDER BY i.due_date, i.id", params).fetchall()
    out = []
    for r in rows:
        days_past_due = (today - date.fromisoformat(r["due_date"])).days
        out.append({
            "invoice_id": r["id"],
            "vendor_id": r["vendor_id"],
            "vendor_name": r["vendor_name"],
            "amount": r["amount"],
            "due_date": r["due_date"],
            "description": r["description"],
            "is_overdue": days_past_due > 0,
            "days_overdue": max(days_past_due, 0),
        })
    return out


def _vendor_row(conn: sqlite3.Connection, row: sqlite3.Row, today: date) -> dict:
    open_invoices = _open_invoices(conn, today, row["id"])
    return {
        "vendor_id": row["id"],
        "name": row["name"],
        "specialty": row["specialty"],
        "lead_days": row["lead_days"],
        "open_invoice_count": len(open_invoices),
        "blocked": bool(open_invoices),
    }


def _pending_requests(conn: sqlite3.Connection) -> list[dict]:
    if not _table_exists(conn, "approval_requests"):
        return []
    return [dict(r) for r in conn.execute(
        "SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY id"
    )]


def _balance(conn: sqlite3.Connection) -> float | None:
    row = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (CASH_ACCOUNT,)).fetchone()
    return None if row is None else row["balance"]


# ---------------------------------------------------------------- read tools

@mcp.tool(annotations=READ_ONLY)
def get_today() -> dict:
    """Return the shop's 'today' (desk.date_today) and any desk notes (read-only).

    Always use this date, never the real calendar date, to judge what is
    overdue, how many days until something is due, and restock arrival dates.
    """
    with closing(_connect()) as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
    if row is None:
        return _not_found("desk table has no date_today row.")
    return {"found": True, "date_today": row["date_today"], "notes": row["notes"]}


@mcp.tool(annotations=READ_ONLY)
def list_open_tickets() -> dict:
    """List every ticket on the board that is not resolved (read-only).

    Use this to see the work queue. Each ticket shows id, type, requester,
    subject, status, and its links (sku/size/qty, lease_id, invoice_id).
    Call get_ticket(ticket_id) for the full ticket with notes and drafts.
    """
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id,
                   status, created_at
            FROM tickets WHERE status != 'resolved' ORDER BY created_at, id
            """
        ).fetchall()
    return {"count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool(annotations=READ_ONLY)
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket with everything on the board for it (read-only).

    Returns the ticket fields (type, requester, subject, sku, size, qty,
    lease_id, invoice_id, status, notes, created_at), plus agent notes,
    saved customer drafts, and approval requests that mention it. Use the
    linked ids to call get_invoice, get_lease, or check_stock. Returns
    found=False if the ticket does not exist.
    """
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return _not_found(f"Ticket {ticket_id} not found.")
        notes = drafts = []
        if _table_exists(conn, "ticket_notes"):
            notes = [dict(r) for r in conn.execute(
                "SELECT id, author, note, created_on FROM ticket_notes WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            )]
        if _table_exists(conn, "customer_drafts"):
            drafts = [dict(r) for r in conn.execute(
                "SELECT id, draft, status, created_on FROM customer_drafts WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            )]
        requests = []
        if _table_exists(conn, "approval_requests"):
            requests = [dict(r) for r in conn.execute(
                "SELECT id, kind, ref_id, amount, status, requested_by, decided_by FROM approval_requests "
                "WHERE ticket_id = ? ORDER BY id",
                (ticket_id,),
            )]
    return {"found": True, "ticket": dict(row), "agent_notes": notes, "customer_drafts": drafts,
            "approval_requests": requests}


@mcp.tool(annotations=READ_ONLY)
def list_tickets() -> dict:
    """List every ticket on the board, including resolved ones (read-only).

    Each ticket shows id, type, requester, subject, its links (sku/size/qty,
    lease_id, invoice_id), status, the requester's notes, and created_at.
    """
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id, status, notes, created_at "
            "FROM tickets ORDER BY created_at, id"
        ).fetchall()
    return {"count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool(annotations=READ_ONLY)
def get_invoice(invoice_id: int) -> dict:
    """Look up one vendor invoice and the vendor who sent it (read-only).

    Use this when a ticket references an invoice_id, or to find out whether a
    vendor is blocked: a vendor will NOT ship new product while it has an open
    (unpaid) invoice. Example: ticket 101 needs a tee reprint from the vendor
    on invoice 501, so check this invoice before promising a restock.

    Returns amount, due_date, status, description, vendor name, specialty, and
    lead_days, plus days_overdue / is_overdue computed against desk.date_today
    (overdue = still open and past due_date). Returns found=False if the
    invoice_id does not exist.
    """
    with closing(_connect()) as conn:
        today = _today(conn)
        row = conn.execute(
            """
            SELECT i.id, i.amount, i.due_date, i.status, i.description,
                   v.id AS vendor_id, v.name AS vendor_name,
                   v.specialty AS vendor_specialty, v.lead_days AS vendor_lead_days
            FROM invoices AS i
            LEFT JOIN vendors AS v ON v.id = i.vendor_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()

    if row is None:
        return _not_found(f"Invoice {invoice_id} not found.")

    days_past_due = (today - date.fromisoformat(row["due_date"])).days
    is_open = row["status"] == "open"
    is_overdue = is_open and days_past_due > 0

    return {
        "found": True,
        "invoice_id": row["id"],
        "amount": row["amount"],
        "due_date": row["due_date"],
        "status": row["status"],
        "description": row["description"],
        "vendor_id": row["vendor_id"],
        "vendor_name": row["vendor_name"],
        "vendor_specialty": row["vendor_specialty"],
        "vendor_lead_days": row["vendor_lead_days"],
        "today": today.isoformat(),
        "is_overdue": is_overdue,
        "days_overdue": days_past_due if is_overdue else 0,
        "vendor_blocked": is_open,
    }


@mcp.tool(annotations=READ_ONLY)
def get_lease(lease_id: int) -> dict:
    """Look up one shop lease and when its rent is next due (read-only).

    Use this for rent notices or any question about the shop space. Example:
    ticket 102 is a rent notice for lease 1 from the landlord.

    Returns space_name, landlord, monthly_rent, next_due, and notes, plus
    days_until_due (negative means overdue) and is_overdue, computed against
    desk.date_today. Returns found=False if the lease_id does not exist.
    """
    with closing(_connect()) as conn:
        today = _today(conn)
        row = conn.execute(
            """
            SELECT id, space_name, landlord, monthly_rent, next_due, notes
            FROM leases
            WHERE id = ?
            """,
            (lease_id,),
        ).fetchone()

    if row is None:
        return _not_found(f"Lease {lease_id} not found.")

    days_until_due = (date.fromisoformat(row["next_due"]) - today).days

    return {
        "found": True,
        "lease_id": row["id"],
        "space_name": row["space_name"],
        "landlord": row["landlord"],
        "monthly_rent": row["monthly_rent"],
        "next_due": row["next_due"],
        "notes": row["notes"],
        "today": today.isoformat(),
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
        "days_overdue": max(0, -days_until_due),
    }


@mcp.tool(annotations=READ_ONLY)
def check_stock(sku: str, size: str, qty_needed: int | None = None) -> dict:
    """Check stock on hand for one SKU in one size (read-only).

    Use this before promising any customer order or quote. Sizes are exact
    codes such as S, M, L, XL, or OS (one size). Example: ticket 103 asks for
    20 CC-HOOD-NAVY in size M, so call check_stock("CC-HOOD-NAVY", "M", 20).

    Returns item name, qty_on_hand, and location. If qty_needed is given, also
    returns shortfall = max(qty_needed - qty_on_hand, 0) and can_fulfill.
    Returns found=False if the SKU or size does not exist (listing the sizes
    that do exist for a known SKU).
    """
    if qty_needed is not None and qty_needed < 0:
        return {"found": False, "error": "qty_needed cannot be negative."}

    with closing(_connect()) as conn:
        row = conn.execute(
            """
            SELECT sku, name, size, qty, location
            FROM inventory
            WHERE sku = ? AND size = ?
            """,
            (sku, size),
        ).fetchone()
        if row is None:
            sizes = [
                r["size"]
                for r in conn.execute(
                    "SELECT size FROM inventory WHERE sku = ? ORDER BY rowid", (sku,)
                )
            ]

    if row is None:
        if sizes:
            return _not_found(
                f"Size {size!r} not found for SKU {sku}. Sizes on record: {', '.join(sizes)}."
            )
        return _not_found(f"SKU {sku!r} not found in inventory.")

    result = {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "qty_on_hand": row["qty"],
        "location": row["location"],
    }
    if qty_needed is not None:
        result["qty_needed"] = qty_needed
        result["shortfall"] = max(qty_needed - row["qty"], 0)
        result["can_fulfill"] = row["qty"] >= qty_needed
    return result


@mcp.tool(annotations=READ_ONLY)
def get_pricing(sku: str, proposed_price: float | None = None, qty: int | None = None) -> dict:
    """Get unit cost, list price, and margin for a SKU, optionally at a discount (read-only).

    Pricing is per SKU and is the same for every size. Margin = price - unit_cost.
    Pass proposed_price to check a discount: returns the margin at that price,
    the discount off list, and below_cost=True if the price is under unit cost
    (a price below unit cost must never be approved). Pass qty to also get
    order totals. Example for ticket 103: get_pricing("CC-HOOD-NAVY", 50.0, 20).
    Returns found=False if the SKU has no pricing row.
    """
    if proposed_price is not None and proposed_price < 0:
        return {"found": False, "error": "proposed_price cannot be negative."}
    if qty is not None and qty <= 0:
        return {"found": False, "error": "qty must be positive."}

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
    if row is None:
        return _not_found(f"No pricing found for SKU {sku!r}.")

    cost, list_price = row["unit_cost"], row["list_price"]
    result = {
        "found": True,
        "sku": row["sku"],
        "unit_cost": cost,
        "list_price": list_price,
        "list_margin": round(list_price - cost, 2),
        "list_margin_pct": round((list_price - cost) / list_price * 100, 1) if list_price else None,
    }
    if proposed_price is not None:
        result.update({
            "proposed_price": proposed_price,
            "discount_pct_off_list": round((list_price - proposed_price) / list_price * 100, 1) if list_price else None,
            "proposed_margin": round(proposed_price - cost, 2),
            "proposed_margin_pct": round((proposed_price - cost) / proposed_price * 100, 1) if proposed_price else None,
            "below_cost": proposed_price < cost,
        })
    if qty is not None:
        price = proposed_price if proposed_price is not None else list_price
        result.update({
            "qty": qty,
            "order_total": round(price * qty, 2),
            "order_cost": round(cost * qty, 2),
            "order_margin": round((price - cost) * qty, 2),
        })
    return result


@mcp.tool(annotations=READ_ONLY)
def list_vendors() -> dict:
    """List every vendor with specialty, lead_days, and whether it is blocked (read-only).

    lead_days comes from the vendors table and is how long a restock takes.
    blocked=True means the vendor has an open unpaid invoice and will NOT ship.
    """
    with closing(_connect()) as conn:
        today = _today(conn)
        rows = conn.execute("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id").fetchall()
        vendors = [_vendor_row(conn, r, today) for r in rows]
    return {"count": len(vendors), "vendors": vendors}


@mcp.tool(annotations=READ_ONLY)
def find_vendors(specialty: str) -> dict:
    """Find vendors whose specialty contains the given text (read-only, case-insensitive).

    Use this to pick a restock vendor: e.g. "apparel" for tees and hoodies,
    "mugs" for mugs. Each match shows lead_days and blocked (open unpaid
    invoice = will not ship). Returns an empty list if nothing matches; never
    assume a vendor that isn't listed.
    """
    term = (specialty or "").strip()
    if not term:
        return {"count": 0, "vendors": [], "error": "specialty cannot be empty."}
    with closing(_connect()) as conn:
        today = _today(conn)
        rows = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors "
            "WHERE lower(specialty) LIKE '%' || lower(?) || '%' ORDER BY lead_days, id",
            (term,),
        ).fetchall()
        vendors = [_vendor_row(conn, r, today) for r in rows]
    return {"specialty_query": term, "count": len(vendors), "vendors": vendors}


@mcp.tool(annotations=READ_ONLY)
def get_vendor_open_invoices(vendor_id: int) -> dict:
    """List a vendor's open (unpaid) invoices and whether it is blocked (read-only).

    A vendor will NOT ship new product while it has any open invoice, so
    check this before requesting a restock or purchase order. Returns each
    open invoice with amount, due_date, and days_overdue (vs desk.date_today),
    plus the total owed. Returns found=False if the vendor does not exist.
    """
    with closing(_connect()) as conn:
        today = _today(conn)
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return _not_found(f"Vendor {vendor_id} not found.")
        invoices = _open_invoices(conn, today, vendor_id)
    return {
        "found": True,
        "vendor_id": vendor["id"],
        "vendor_name": vendor["name"],
        "lead_days": vendor["lead_days"],
        "today": today.isoformat(),
        "open_invoices": invoices,
        "total_open": round(sum(i["amount"] for i in invoices), 2),
        "blocked": bool(invoices),
    }


@mcp.tool(annotations=READ_ONLY)
def get_cash_balance() -> dict:
    """Get the cash balance and how much is already spoken for (read-only).

    Returns each cash account, the checking balance, the totals of PENDING
    payment and purchase-order requests (both are paid from checking once a
    human approves), and available_after_pending (balance minus everything
    pending). Cash only goes out in this shop; there is no revenue, and a
    balance can never go negative.
    """
    with closing(_connect()) as conn:
        today = _today(conn)
        accounts = [dict(r) for r in conn.execute("SELECT name, balance, date FROM cash_accounts")]
        balance = _balance(conn)
        pending = _pending_requests(conn)
    pending_payments = [p for p in pending if p["kind"] in PAYMENT_KINDS]
    pending_pos = [p for p in pending if p["kind"] == "purchase_order"]
    pending_total = round(sum(p["amount"] for p in pending), 2)
    return {
        "today": today.isoformat(),
        "accounts": accounts,
        "checking_balance": balance,
        "pending_requests": len(pending),
        "pending_payment_total": round(sum(p["amount"] for p in pending_payments), 2),
        "pending_purchase_order_total": round(sum(p["amount"] for p in pending_pos), 2),
        "pending_total": pending_total,
        "available_after_pending": None if balance is None else round(balance - pending_total, 2),
    }


@mcp.tool(annotations=READ_ONLY)
def list_payments() -> dict:
    """List every payment made so far, newest first, with the checking balance (read-only).

    Each payment row was created by a human-approved execute_payment.
    """
    with closing(_connect()) as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, kind, ref_id, amount, account, paid_at, approved_by FROM payments ORDER BY id DESC"
        )]
        balance = _balance(conn)
    return {"checking_balance": balance, "count": len(rows),
            "total_paid": round(sum(r["amount"] for r in rows), 2), "payments": rows}


@mcp.tool(annotations=READ_ONLY)
def list_obligations(days_ahead: int = 30) -> dict:
    """List everything the shop owes: open invoices plus rent due soon (read-only).

    Use this before recommending any payment, so cash is checked against ALL
    obligations, not just one bill. Includes every open invoice (overdue ones
    first) and each lease whose rent is due within days_ahead of
    desk.date_today. Returns the total owed, the checking balance, and
    cash_after_all (negative means the shop cannot pay everything).
    """
    if days_ahead < 0:
        return {"error": "days_ahead cannot be negative."}
    with closing(_connect()) as conn:
        today = _today(conn)
        invoices = _open_invoices(conn, today)
        leases = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due FROM leases ORDER BY next_due"
        ).fetchall()
        balance = _balance(conn)

    items = [{
        "kind": "invoice", "ref_id": i["invoice_id"], "payee": i["vendor_name"],
        "amount": i["amount"], "due_date": i["due_date"],
        "days_until_due": -i["days_overdue"] if i["is_overdue"]
        else (date.fromisoformat(i["due_date"]) - today).days,
        "is_overdue": i["is_overdue"], "description": i["description"],
    } for i in invoices]
    for lease in leases:
        days_until = (date.fromisoformat(lease["next_due"]) - today).days
        if days_until <= days_ahead:
            items.append({
                "kind": "rent", "ref_id": lease["id"], "payee": lease["landlord"],
                "amount": lease["monthly_rent"], "due_date": lease["next_due"],
                "days_until_due": days_until, "is_overdue": days_until < 0,
                "description": f"Rent for {lease['space_name']}",
            })
    items.sort(key=lambda x: (x["days_until_due"], x["ref_id"]))
    total = round(sum(x["amount"] for x in items), 2)
    return {
        "today": today.isoformat(),
        "days_ahead": days_ahead,
        "obligations": items,
        "total_owed": total,
        "checking_balance": balance,
        "cash_after_all": None if balance is None else round(balance - total, 2),
    }


@mcp.tool(annotations=READ_ONLY)
def list_approval_requests(status: str | None = None) -> dict:
    """List payment and purchase-order requests waiting on (or decided by) a human (read-only).

    status can be 'pending', 'executed', or 'rejected'; omit it for all.
    Each request includes its ticket (id, subject, requester), kind, amount,
    reason, and the agent that asked. Check this before requesting a payment
    so you don't create a duplicate.
    """
    if status is not None and status not in ("pending", "executed", "rejected"):
        return {"error": "status must be pending, executed, or rejected."}
    with closing(_connect()) as conn:
        if not _table_exists(conn, "approval_requests"):
            return {"count": 0, "requests": []}
        sql = """
            SELECT r.*, t.subject AS ticket_subject, t.requester AS ticket_requester,
                   v.name AS vendor_name,
                   CASE r.kind
                     WHEN 'invoice' THEN (SELECT v2.name FROM invoices AS i JOIN vendors AS v2 ON v2.id = i.vendor_id
                                          WHERE i.id = r.ref_id)
                     WHEN 'rent' THEN (SELECT l.landlord FROM leases AS l WHERE l.id = r.ref_id)
                     ELSE v.name
                   END AS payee,
                   CASE r.kind
                     WHEN 'invoice' THEN (SELECT 'Invoice ' || i.id || ': ' || i.description FROM invoices AS i
                                          WHERE i.id = r.ref_id)
                     WHEN 'rent' THEN (SELECT 'Rent: ' || l.space_name || ' (due ' || l.next_due || ')'
                                       FROM leases AS l WHERE l.id = r.ref_id)
                     ELSE 'PO: ' || r.qty || ' x ' || r.sku || ' ' || r.size
                   END AS memo
            FROM approval_requests AS r
            LEFT JOIN tickets AS t ON t.id = r.ticket_id
            LEFT JOIN vendors AS v ON v.id = r.vendor_id
        """
        params: tuple = ()
        if status:
            sql, params = sql + " WHERE r.status = ?", (status,)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY r.id", params)]
    return {"count": len(rows), "requests": rows}


# ---------------------------------------------------------------- agent write tools

@mcp.tool(annotations=AGENT_WRITE)
def add_ticket_note(ticket_id: int, author: str, note: str) -> dict:
    """Add a note to a ticket on the board (used by Boss to log decisions).

    Notes are internal and are never sent to anyone. They are stored in the
    ticket_notes table, dated with desk.date_today.
    """
    try:
        author, note = _clean_text(author, "author"), _clean_text(note, "note")
    except ValueError as e:
        return _refuse(str(e))
    with closing(_connect_rw()) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return _refuse(f"Ticket {ticket_id} not found.")
        today = _today(conn).isoformat()
        cur = conn.execute(
            "INSERT INTO ticket_notes (ticket_id, author, note, created_on) VALUES (?, ?, ?, ?)",
            (ticket_id, author, note, today),
        )
    return {"ok": True, "note_id": cur.lastrowid, "ticket_id": ticket_id, "created_on": today}


@mcp.tool(annotations=AGENT_WRITE)
def update_ticket_status(ticket_id: int, status: str) -> dict:
    """Set a ticket's status (used by Boss).

    Allowed statuses: open, in_progress, waiting_on_approval,
    waiting_on_restock, resolved. Use waiting_on_approval when a payment or
    purchase order is pending a human decision; use resolved only when
    nothing is left to do or approve.
    """
    if status not in TICKET_STATUSES:
        return _refuse(f"Invalid status {status!r}. Allowed: {', '.join(TICKET_STATUSES)}.")
    with closing(_connect_rw()) as conn:
        row = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return _refuse(f"Ticket {ticket_id} not found.")
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    return {"ok": True, "ticket_id": ticket_id, "old_status": row["status"], "new_status": status}


@mcp.tool(annotations=AGENT_WRITE)
def save_customer_draft(ticket_id: int, draft: str) -> dict:
    """Save Customer Service's draft message on the ticket board. It is NEVER sent.

    The draft stays on the board with status 'draft_not_sent' for a human to
    review. There is no tool that emails or messages customers or vendors.
    """
    try:
        draft = _clean_text(draft, "draft")
    except ValueError as e:
        return _refuse(str(e))
    with closing(_connect_rw()) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return _refuse(f"Ticket {ticket_id} not found.")
        today = _today(conn).isoformat()
        cur = conn.execute(
            "INSERT INTO customer_drafts (ticket_id, draft, created_on) VALUES (?, ?, ?)",
            (ticket_id, draft, today),
        )
    return {"ok": True, "draft_id": cur.lastrowid, "ticket_id": ticket_id,
            "status": "draft_not_sent", "sent": False, "created_on": today}


@mcp.tool(annotations=AGENT_WRITE)
def request_payment(ticket_id: int, kind: str, ref_id: int, amount: float, reason: str,
                    requested_by: str) -> dict:
    """Create a PENDING payment request for a human to approve. Moves NO money.

    ticket_id is the ticket this payment resolves. kind is 'invoice'
    (ref_id = invoices.id) or 'rent' (ref_id = leases.id). amount must exactly
    match the open invoice amount or the lease's monthly_rent; the tool refuses
    anything else, an invoice that isn't open, a duplicate pending request, or
    an amount larger than the cash balance. Returns the request_id and the cash
    position after all pending requests.
    """
    if kind not in PAYMENT_KINDS:
        return _refuse(f"kind must be one of {PAYMENT_KINDS}.")
    try:
        reason, requested_by = _clean_text(reason, "reason"), _clean_text(requested_by, "requested_by")
    except ValueError as e:
        return _refuse(str(e))
    if amount is None or amount <= 0:
        return _refuse("amount must be positive.")

    with closing(_connect_rw()) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return _refuse(f"Ticket {ticket_id} not found.")
        today = _today(conn).isoformat()
        if kind == "invoice":
            target = conn.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if target is None:
                return _refuse(f"Invoice {ref_id} not found.")
            if target["status"] != "open":
                return _refuse(f"Invoice {ref_id} is {target['status']}, not open.")
            expected = target["amount"]
        else:
            target = conn.execute("SELECT monthly_rent FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if target is None:
                return _refuse(f"Lease {ref_id} not found.")
            expected = target["monthly_rent"]
        if abs(amount - expected) > 0.005:
            return _refuse(f"amount {amount} does not match the amount owed ({expected}).",
                           amount_owed=expected)

        dup = conn.execute(
            "SELECT id FROM approval_requests WHERE kind = ? AND ref_id = ? AND status = 'pending'",
            (kind, ref_id),
        ).fetchone()
        if dup:
            return _refuse(f"A pending request already exists for this {kind} (request {dup['id']}).",
                           request_id=dup["id"])

        balance = _balance(conn)
        if balance is None or amount > balance:
            return _refuse(f"Not enough cash: balance {balance}, amount {amount}.", checking_balance=balance)

        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, ref_id, amount, reason, requested_by, created_on) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, kind, ref_id, amount, reason, requested_by, today),
        )
        pending_total = sum(p["amount"] for p in _pending_requests(conn))

    return {
        "ok": True,
        "request_id": cur.lastrowid,
        "ticket_id": ticket_id,
        "status": "pending",
        "kind": kind,
        "ref_id": ref_id,
        "amount": amount,
        "money_moved": False,
        "checking_balance": balance,
        "pending_total": round(pending_total, 2),
        "available_after_pending": round(balance - pending_total, 2),
        "note": "Pending human approval. No money has moved.",
    }


@mcp.tool(annotations=AGENT_WRITE)
def request_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int, reason: str,
                           requested_by: str) -> dict:
    """Create a PENDING restock purchase order for a human to approve. Moves NO money.

    ticket_id is the ticket the restock is for. The PO amount is calculated
    and stored as qty x unit_cost from pricing; when a human approves it, that
    amount is paid from checking. Refuses if the vendor has an open unpaid
    invoice (blocked vendors will not ship), if the SKU/size doesn't exist, if
    qty isn't positive, or if the amount is more than the cash still available
    after all pending requests. Returns the request_id and the expected
    arrival date (desk.date_today + lead_days).
    """
    try:
        reason, requested_by = _clean_text(reason, "reason"), _clean_text(requested_by, "requested_by")
    except ValueError as e:
        return _refuse(str(e))
    if qty is None or qty <= 0:
        return _refuse("qty must be positive.")

    with closing(_connect_rw()) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return _refuse(f"Ticket {ticket_id} not found.")
        today = _today(conn)
        vendor = conn.execute(
            "SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return _refuse(f"Vendor {vendor_id} not found.")
        open_invoices = _open_invoices(conn, today, vendor_id)
        if open_invoices:
            return _refuse(
                f"{vendor['name']} has open unpaid invoice(s) "
                f"{[i['invoice_id'] for i in open_invoices]} and will not ship until they are paid.",
                vendor_blocked=True, open_invoices=open_invoices,
            )
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return _refuse(f"SKU {sku!r} size {size!r} not found in inventory.")
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return _refuse(f"No pricing found for SKU {sku!r}, so the PO amount can't be calculated.")
        amount = round(price["unit_cost"] * qty, 2)

        balance = _balance(conn) or 0.0
        pending_total = sum(p["amount"] for p in _pending_requests(conn))
        available = round(balance - pending_total, 2)
        if amount > available:
            return _refuse(
                f"PO amount {amount} ({qty} x {price['unit_cost']}) is more than cash available "
                f"after pending requests ({available}).",
                amount=amount, available_after_pending=available,
            )

        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, ref_id, amount, reason, requested_by, created_on, "
            "vendor_id, sku, size, qty) VALUES (?, 'purchase_order', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, vendor_id, amount, reason, requested_by, today.isoformat(), vendor_id, sku, size, qty),
        )
    return {
        "ok": True,
        "request_id": cur.lastrowid,
        "ticket_id": ticket_id,
        "status": "pending",
        "vendor_id": vendor_id,
        "vendor": vendor["name"],
        "sku": sku, "size": size, "qty": qty,
        "unit_cost": price["unit_cost"],
        "amount": amount,
        "available_after_pending": round(available - amount, 2),
        "expected_arrival_if_approved_today": date.fromordinal(today.toordinal() + vendor["lead_days"]).isoformat(),
        "money_moved": False,
        "note": "Pending human approval. Nothing has been ordered or paid.",
    }


# ---------------------------------------------------------------- human-only tools
# Never give these to an agent. Only the backend's human-approval step calls them.

@mcp.tool(annotations=HUMAN_ONLY, tags={"human_only"})
def execute_payment(request_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Execute an approved request. The only tool that moves money.

    Handles invoice, rent, and purchase_order requests. Requires a pending
    request and a human approver name (agent or system names are refused).
    Refuses if the checking balance is too small (cash can never go negative)
    and refuses a purchase order if the vendor has an open unpaid invoice.
    In one transaction it: inserts a payments row (paid_at = desk.date_today,
    account = checking), lowers the checking balance, marks the invoice paid /
    moves the lease's next_due ahead one month / (for a PO) changes no stock,
    marks the request executed, and adds a note to the linked ticket.
    """
    if not _is_human_name(approved_by):
        return _refuse(f"approved_by {approved_by!r} is not a human name. Only a person can approve payments.")
    approver = approved_by.strip()

    conn = _connect_rw()
    try:
        conn.execute("BEGIN IMMEDIATE")

        def refuse(message: str, **extra) -> dict:
            conn.execute("ROLLBACK")
            return _refuse(message, **extra)

        req = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            return refuse(f"Request {request_id} not found.")
        if req["status"] != "pending":
            return refuse(f"Request {request_id} is {req['status']}, not pending.")
        if req["kind"] not in REQUEST_KINDS:
            return refuse(f"Request {request_id} has unknown kind {req['kind']!r}.")

        today_d = _today(conn)
        today = today_d.isoformat()
        amount = req["amount"]
        balance = _balance(conn)
        if balance is None or amount > balance:
            return refuse(f"Not enough cash: balance {balance}, payment {amount}. Balance can never go negative.",
                          checking_balance=balance)

        if req["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return refuse(f"Invoice {req['ref_id']} is no longer open.")
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
            target = {"invoice_id": req["ref_id"], "invoice_status": "paid"}
            what = f"invoice {req['ref_id']}"
        elif req["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
            if lease is None:
                return refuse(f"Lease {req['ref_id']} not found.")
            new_due = _add_month(date.fromisoformat(lease["next_due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, req["ref_id"]))
            target = {"lease_id": req["ref_id"], "old_next_due": lease["next_due"], "new_next_due": new_due}
            what = f"rent on lease {req['ref_id']} (next due now {new_due})"
        else:  # purchase_order
            vendor = conn.execute("SELECT name, lead_days FROM vendors WHERE id = ?", (req["vendor_id"],)).fetchone()
            if vendor is None:
                return refuse(f"Vendor {req['vendor_id']} not found.")
            blocking = _open_invoices(conn, today_d, req["vendor_id"])
            if blocking:
                return refuse(f"{vendor['name']} has open unpaid invoice(s) {[i['invoice_id'] for i in blocking]}; "
                              "the purchase order cannot be placed.", vendor_blocked=True)
            arrival = date.fromordinal(today_d.toordinal() + vendor["lead_days"]).isoformat()
            target = {"vendor": vendor["name"], "sku": req["sku"], "size": req["size"], "qty": req["qty"],
                      "expected_arrival": arrival, "stock_changed": False}
            what = (f"PO to {vendor['name']} for {req['qty']} x {req['sku']} {req['size']} "
                    f"(arrives about {arrival}; stock not added until it arrives)")

        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (req["kind"], req["ref_id"] if req["kind"] != "purchase_order" else request_id,
             amount, CASH_ACCOUNT, today, approver),
        )
        payment_id = cur.lastrowid
        updated = conn.execute(
            "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ? AND balance >= ?",
            (amount, today, CASH_ACCOUNT, amount),
        )
        if updated.rowcount != 1:
            return refuse("Cash balance changed and is no longer enough. Nothing was paid.")
        conn.execute(
            "UPDATE approval_requests SET status = 'executed', decided_by = ?, decided_on = ?, payment_id = ? "
            "WHERE id = ?",
            (approver, today, payment_id, request_id),
        )
        new_balance = _balance(conn)
        conn.execute(
            "INSERT INTO ticket_notes (ticket_id, author, note, created_on) VALUES (?, ?, ?, ?)",
            (req["ticket_id"], approver,
             f"Approved and paid ${amount:,.2f} for {what} (request {request_id}, payment {payment_id}). "
             f"Checking balance ${balance:,.2f} -> ${new_balance:,.2f}.", today),
        )
        remaining = conn.execute(
            "SELECT count(*) AS n FROM approval_requests WHERE ticket_id = ? AND status = 'pending'",
            (req["ticket_id"],),
        ).fetchone()["n"]
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "request_id": request_id,
        "ticket_id": req["ticket_id"],
        "payment_id": payment_id,
        "kind": req["kind"],
        "amount": amount,
        "paid_at": today,
        "approved_by": approver,
        "old_balance": balance,
        "new_balance": new_balance,
        "pending_left_on_ticket": remaining,
        **target,
    }


@mcp.tool(annotations=HUMAN_ONLY, tags={"human_only"})
def reject_request(request_id: int, rejected_by: str, reason: str) -> dict:
    """HUMAN ONLY. Reject a pending payment or purchase-order request. Moves no money.

    Marks the request rejected and adds a note to the linked ticket.
    """
    if not _is_human_name(rejected_by):
        return _refuse(f"rejected_by {rejected_by!r} is not a human name.")
    try:
        reason = _clean_text(reason, "reason")
    except ValueError as e:
        return _refuse(str(e))
    who = rejected_by.strip()
    with closing(_connect_rw()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        req = conn.execute(
            "SELECT ticket_id, kind, amount FROM approval_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
        if req is None:
            conn.execute("ROLLBACK")
            return _refuse(f"Request {request_id} not found or not pending.")
        today = _today(conn).isoformat()
        conn.execute(
            "UPDATE approval_requests SET status = 'rejected', decided_by = ?, decided_on = ?, "
            "reason = reason || ' | Rejected: ' || ? WHERE id = ?",
            (who, today, reason, request_id),
        )
        conn.execute(
            "INSERT INTO ticket_notes (ticket_id, author, note, created_on) VALUES (?, ?, ?, ?)",
            (req["ticket_id"], who,
             f"Rejected {req['kind']} request {request_id} (${req['amount']:,.2f}). No money moved. Reason: {reason}",
             today),
        )
        remaining = conn.execute(
            "SELECT count(*) AS n FROM approval_requests WHERE ticket_id = ? AND status = 'pending'",
            (req["ticket_id"],),
        ).fetchone()["n"]
        conn.execute("COMMIT")
    return {"ok": True, "request_id": request_id, "ticket_id": req["ticket_id"], "status": "rejected",
            "rejected_by": who, "money_moved": False, "pending_left_on_ticket": remaining}


if __name__ == "__main__":
    mcp.run(show_banner=False)
