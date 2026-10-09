# Campus Customs MCP Server

A [FastMCP](https://gofastmcp.com) server that gives the Campus Customs agents tools to read and update the shop board.

- **Database:** `data/campus_customs_new.db` (the working copy). The path is built from `server.py`'s own location, so the server works from any folder. The original `data/campus_customs.db` is never opened.
- **"Today":** Every date calculation uses `desk.date_today`, never the system clock. Notes, drafts, requests, and payments are dated with it too.
- **No guessing:** Unknown IDs, SKUs, or sizes return `found: false` (read tools) or `refused: true` (write tools) with a clear error.
- **Parameterized SQL** everywhere. Read tools open the database in SQLite read-only mode.
- **Board tables:** On first write, the server creates `approval_requests` (every row has a `ticket_id`), `ticket_notes`, and `customer_drafts` in the working copy. Running `python reset_db.py` clears them.

## Read tools (any agent, no changes)

| Tool | Inputs | Reads | Returns |
|---|---|---|---|
| `get_today` | none | desk | `date_today`, desk notes |
| `list_open_tickets` | none | tickets | Every non-resolved ticket with its links |
| `list_tickets` | none | tickets | Every ticket, including resolved (for the board) |
| `get_ticket` | `ticket_id` | tickets, ticket_notes, customer_drafts, approval_requests | Full ticket plus notes, saved drafts, and its approval requests |
| `get_invoice` | `invoice_id` | invoices, vendors, desk | Amount, due date, status, vendor, `is_overdue`, `days_overdue`, `vendor_blocked` |
| `get_lease` | `lease_id` | leases, desk | Space, landlord, rent, next due, `days_until_due`, `is_overdue` |
| `check_stock` | `sku`, `size`, `qty_needed?` | inventory | Name, qty on hand, location; plus `shortfall` and `can_fulfill` when `qty_needed` is given |
| `get_pricing` | `sku`, `proposed_price?`, `qty?` | pricing | Unit cost, list price, margin. With `proposed_price`: discount %, margin at that price, `below_cost`. With `qty`: order totals. |
| `list_vendors` | none | vendors, invoices | Every vendor with `lead_days` and `blocked` |
| `find_vendors` | `specialty` | vendors, invoices | Vendors whose specialty matches (case-insensitive), fastest first, with `blocked` |
| `get_vendor_open_invoices` | `vendor_id` | vendors, invoices, desk | Open invoices, total owed, `blocked` |
| `get_cash_balance` | none | cash_accounts, approval_requests | Checking balance, pending payment and PO totals, `available_after_pending` |
| `list_payments` | none | payments, cash_accounts | Every payment made, newest first, and the balance |
| `list_obligations` | `days_ahead?` (default 30) | invoices, vendors, leases, cash_accounts | All open invoices plus rent due soon, most urgent first, `total_owed`, `cash_after_all` |
| `list_approval_requests` | `status?` | approval_requests, tickets, vendors | Requests with their ticket, amount, reason, and the agent that asked |

## Agent write tools (no money moves, nothing is sent)

| Tool | Inputs | Writes | Safety |
|---|---|---|---|
| `add_ticket_note` | `ticket_id`, `author`, `note` | ticket_notes | Internal note only |
| `update_ticket_status` | `ticket_id`, `status` | tickets.status | Allowed statuses: `open`, `in_progress`, `waiting_on_approval`, `waiting_on_restock`, `resolved` |
| `save_customer_draft` | `ticket_id`, `draft` | customer_drafts | Saved as `draft_not_sent`. There is no send tool. |
| `request_payment` | `ticket_id`, `kind` (`invoice`/`rent`), `ref_id`, `amount`, `reason`, `requested_by` | approval_requests (pending) | Refuses: amount different from what's owed, invoice not open, duplicate pending request, amount larger than cash |
| `request_purchase_order` | `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `reason`, `requested_by` | approval_requests (pending, amount = qty × unit_cost) | Refuses: vendor has an open unpaid invoice, unknown SKU/size, amount more than cash left after pending requests. Returns the expected arrival date (today + lead_days). |

## Human-only tools (never given to an agent)

Only the backend's human-approval step calls these. They're tagged `human_only`.

| Tool | Inputs | What it does |
|---|---|---|
| `execute_payment` | `request_id`, `approved_by` | The **only** tool that moves money. Handles invoice, rent, **and purchase-order** requests. Requires a pending request and a human name (agent or system names like "Accounting" or "Boss agent" are refused). Refuses if the balance would go negative, and refuses a PO if the vendor has an open invoice. In **one transaction** it inserts a `payments` row (paid_at = date_today, account = checking), lowers the balance, marks the invoice `paid` / moves the lease's `next_due` ahead one month / (PO) adds **no** stock since goods arrive after the lead time, marks the request `executed`, and adds a note to the linked ticket. |
| `reject_request` | `request_id`, `rejected_by`, `reason` | Marks a pending request `rejected` and notes it on the ticket. Moves no money. |

## Run

From the project root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python reset_db.py               # fresh working copy
python mcp_server/server.py      # starts the server over stdio
```

Tests (FastMCP in-memory client; no server process needed):

```bash
python tests/test_mcp_tools.py         # original 3 read tools, read-only
python tests/test_mcp_write_tools.py   # all tools incl. refusals; resets the DB before and after
```
