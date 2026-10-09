# Campus Customs Agent Harness

Campus Customs is a small custom apparel shop that sells Yale-themed hoodies, tees, caps, and mugs. A team of five agents (Boss, Inventory, Accounting, Facilities, Customer Service) works the tickets on the shop board, and a human approves every dollar that moves.

- **Data:** the agents read and update `data/campus_customs_new.db` (the working copy) through the MCP server. `data/campus_customs.db` is the original, and it's never modified. `reset_db.py` or `POST /reset` recopies it.
- **"Today":** `desk.date_today` (2026-08-31). Every due date, overdue check, and arrival estimate is judged against this date, never the system clock.

## 1. Tables

### Original tables (from `campus_customs.db`)
| Table | Fields (type) | Why it matters / main user |
|---|---|---|
| **desk** | `date_today TEXT`, `notes TEXT` | The shop's clock, and the only source of "today". **Boss**, **Facilities**. |
| **tickets** | `id INTEGER PK`, `type TEXT`, `requester TEXT`, `subject TEXT`, `sku TEXT`, `size TEXT`, `qty INTEGER`, `lease_id INTEGER → leases`, `invoice_id INTEGER → invoices`, `status TEXT`, `notes TEXT`, `created_at TEXT` | The work queue. Links point a ticket at its stock, lease, or invoice. Status is `open → in_progress → resolved` (`waiting_on_approval` and `waiting_on_restock` are also allowed). **Boss**. |
| **inventory** | `sku TEXT`, `name TEXT`, `size TEXT`, `qty INTEGER`, `location TEXT`, PK `(sku, size)` | Stock on hand per SKU and size. **Inventory**. |
| **pricing** | `sku TEXT PK`, `unit_cost REAL`, `list_price REAL` | One price per SKU (same for every size). Used for margins, the discount floor (never below cost), and PO cost. **Accounting**. |
| **vendors** | `id INTEGER PK`, `name TEXT`, `specialty TEXT`, `lead_days INTEGER` | Who restocks what (matched by `specialty`) and how long it takes (arrival = today + `lead_days`). **Inventory**. |
| **invoices** | `id INTEGER PK`, `vendor_id INTEGER → vendors`, `amount REAL`, `due_date TEXT`, `status TEXT`, `description TEXT` | Bills owed to vendors. A vendor with any `open` invoice will not ship. **Accounting**, **Inventory**. |
| **leases** | `id INTEGER PK`, `space_name TEXT`, `landlord TEXT`, `monthly_rent REAL`, `next_due TEXT`, `notes TEXT` | Rent. `next_due` moves ahead one month when rent is paid. **Facilities**. |
| **cash_accounts** | `name TEXT PK`, `balance REAL`, `date TEXT` | Checking balance. It can never go negative, and no money comes in. **Accounting**. |
| **payments** | `id INTEGER PK`, `kind TEXT`, `ref_id INTEGER`, `amount REAL`, `account TEXT`, `paid_at TEXT`, `approved_by TEXT` | The ledger of executed payments. It's written **only** by the human-only `execute_payment`. `kind` is `invoice`, `rent`, or `purchase_order`. `ref_id` is the invoice id, the lease id, or (for a PO) the approval request id. |

### Board tables (created by the MCP server on first write; cleared by a reset)
| Table | Fields (type) | Purpose |
|---|---|---|
| **approval_requests** | `id INTEGER PK`, `ticket_id INTEGER` (always set), `kind TEXT` (`invoice`/`rent`/`purchase_order`), `ref_id INTEGER`, `amount REAL`, `reason TEXT`, `requested_by TEXT`, `status TEXT` (`pending`/`executed`/`rejected`), `created_on TEXT`, `vendor_id`, `sku`, `size`, `qty`, `decided_by`, `decided_on`, `payment_id` | Pending money requests from agents, waiting on a human |
| **ticket_notes** | `id`, `ticket_id`, `author`, `note`, `created_on` | Boss's decision notes, plus an automatic note on every approval or rejection |
| **customer_drafts** | `id`, `ticket_id`, `draft`, `status` (`draft_not_sent`), `created_on` | Customer Service drafts. They're never sent. |

### Starting state → end of the final run
| | After reset | End of run (in the repo) |
|---|---|---|
| Checking | $3,400.00 | **$160.00** |
| Payments | none | #1 rent $2,400.00 (ticket 102), #2 invoice 501 $840.00 (ticket 101), both approved by Luke |
| Invoice 501 (Bulldog Print Co, $840, due 2026-08-28) | open, 3 days overdue | paid |
| Lease 1 next due | 2026-09-02 | 2026-10-02 |
| Tickets 101 / 102 / 103 | open | resolved |

The three tickets are linked:
- **101** needs a size S tee. There are 0 in stock, and the restock vendor Bulldog Print Co is blocked by invoice 501.
- **102** is $2,400 rent.
- **103** is 20 navy size M hoodies at a bulk discount. There are 8 in stock (12 short), and the restock is about $264 at cost.
- Rent plus invoice 501 leaves **$160**, so the hoodie restock can't be afforded. See `desk_tickets.html` (ticket tabs and Cash tab).

## 2. MCP tools

**Server:** `mcp_server/server.py` (FastMCP, stdio).
- Every query is parameterized.
- Read tools open SQLite in read-only mode.
- Unknown ids, SKUs, or sizes return `found: false` (reads) or `refused: true` (writes). Nothing is guessed.
- Tests: `tests/test_mcp_tools.py` and `tests/test_mcp_write_tools.py` (41 checks).

| Tool | Inputs | Tables used | Used by |
|---|---|---|---|
| `get_today` | none | desk | Boss, Facilities |
| `list_open_tickets` | none | tickets | Boss |
| `list_tickets` | none | tickets | backend |
| `get_ticket` | `ticket_id` | tickets, ticket_notes, customer_drafts, approval_requests | Boss, Customer Service |
| `get_invoice` | `invoice_id` | invoices, vendors, desk | Accounting |
| `get_lease` | `lease_id` | leases, desk | Facilities |
| `check_stock` | `sku`, `size`, `qty_needed?` | inventory | Inventory |
| `get_pricing` | `sku`, `proposed_price?`, `qty?` | pricing | Accounting |
| `list_vendors` | none | vendors, invoices, desk | Inventory |
| `find_vendors` | `specialty` | vendors, invoices, desk | Inventory |
| `get_vendor_open_invoices` | `vendor_id` | vendors, invoices, desk | Inventory, Accounting |
| `get_cash_balance` | none | cash_accounts, approval_requests, desk | Accounting, Facilities, backend |
| `list_obligations` | `days_ahead?` (30) | invoices, vendors, leases, cash_accounts, desk | Accounting |
| `list_approval_requests` | `status?` | approval_requests, tickets, vendors, invoices, leases (adds `payee` and `memo`) | Accounting, backend |
| `list_payments` | none | payments, cash_accounts | backend |
| `add_ticket_note` ✎ | `ticket_id`, `author`, `note` | ticket_notes, tickets | Boss |
| `update_ticket_status` ✎ | `ticket_id`, `status` | tickets | Boss, backend |
| `save_customer_draft` ✎ | `ticket_id`, `draft` | customer_drafts, tickets | Customer Service |
| `request_payment` ✎ | `ticket_id`, `kind`, `ref_id`, `amount`, `reason`, `requested_by` | approval_requests (pending); reads invoices, leases, cash_accounts, tickets | Accounting |
| `request_purchase_order` ✎ | `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `reason`, `requested_by` | approval_requests (pending, amount = qty × unit_cost); reads vendors, invoices, inventory, pricing, cash_accounts | Accounting |
| `execute_payment` 🔒 | `request_id`, `approved_by` | payments, cash_accounts, invoices / leases, approval_requests, ticket_notes, vendors | **Human approval route only** |
| `reject_request` 🔒 | `request_id`, `rejected_by`, `reason` | approval_requests, ticket_notes | **Human approval route only** |

✎ = writes, but never moves money or sends anything. 🔒 = human-only; never given to an agent.

### The three ticket-unlocking tools (built first, in Problem 3)
| Tool (inputs) | Reads | Unlocks | Why it's the right tool |
|---|---|---|---|
| `get_invoice(invoice_id)` | invoices ⨝ vendors, desk | **101** | Ticket 101 carries invoice_id 501. The tool shows the $840 Bulldog Print Co bill (due 2026-08-28) is open and 3 days overdue against date_today, so the only apparel vendor (5-day lead) is blocked from reprinting the size S tee. |
| `get_lease(lease_id)` | leases, desk | **102** | Ticket 102 carries lease_id 1. The tool confirms the $2,400 Chapel Street rent owed to Elm City Properties is due 2026-09-02, 2 days out and not yet overdue. |
| `check_stock(sku, size, qty_needed?)` | inventory | **103** | Ticket 103 needs 20 CC-HOOD-NAVY in size M. The tool returns 8 on hand in Aisle A and a shortfall of 12, so the order can't be filled from stock. |

**What the write tools refuse:**
- **`request_payment`** refuses:
  - an amount that differs from the invoice or rent owed
  - an invoice that isn't open
  - a duplicate pending request
  - an amount over the balance
- **`request_purchase_order`** refuses:
  - a vendor with an open invoice
  - an unknown SKU or size
  - an amount over the cash left after pending requests
- **`execute_payment`** handles invoice, rent, and PO requests, all in one transaction:
  - It refuses non-human approvers, non-pending requests, insufficient cash, and a PO to a blocked vendor.
  - It inserts a payments row, lowers checking, and marks the invoice paid, moves the lease forward a month, or (for a PO) adds no stock, since goods arrive after the lead time.
  - It marks the request executed and notes the ticket.

## 3. The five agents

They're built with PydanticAI in `backend/agents/` (one file per agent, plus `shared.py`), and their prompts are in `backend/prompts/*.md`. All of them use the one model in `backend/config.py`, through Portkey (the OpenAI Responses API).
- Each agent sees a **filtered** view of the MCP server with only its own tools, plus `delegate`.
- **Boss** returns a `TicketDecision`. Specialists return an `AgentReport` (`backend/models.py`).

| Agent | Role | MCP tools | Usually delegates to |
|---|---|---|---|
| **Boss** | Reads the ticket, routes it, makes the final call (approves or declines discounts, never below unit cost), logs one note, and sets the ticket `resolved` | `get_ticket`, `list_open_tickets`, `get_today`, `add_ticket_note`, `update_ticket_status` | Inventory (orders, discounts), Facilities (rent), Accounting (bills, margins), Customer Service (replies) |
| **Inventory** | Stock and shortfall; picks a vendor by specialty and lead time; checks whether the vendor is blocked | `check_stock`, `find_vendors`, `list_vendors`, `get_vendor_open_invoices` | Accounting (vendor blocked by an unpaid invoice) |
| **Accounting** | Checks cash against **all** obligations, puts overdue and urgent items first, checks margins, and creates *pending* payment and PO requests | `get_cash_balance`, `list_obligations`, `get_invoice`, `get_vendor_open_invoices`, `get_pricing`, `list_approval_requests`, `request_payment`, `request_purchase_order` | Facilities (lease), Inventory (stock or vendor) |
| **Facilities** | Leases and rent; days until due against `date_today` | `get_lease`, `get_cash_balance`, `get_today` | Accounting (request the rent payment) |
| **Customer Service** | Honest drafts that promise no unsupported dates or prices; saved on the board, never sent | `get_ticket`, `save_customer_draft` | Nobody unless a fact is missing |

**Delegation** (`delegate(to_agent, task)`):
- Any agent can hand a task to any other.
- Depth is capped at 3 (Boss = 0), and an agent already in the chain can't be called again.
- The task is at most 800 characters, never the chat history.
- Usage is shared across the whole ticket run.

In the final run, Boss called first: Facilities for 102, Inventory for 101 and 103. Totals were 8 delegations and 36 MCP calls (see the Reflection tab).

## 4. API routes

The routes are in `backend/main.py` (FastAPI). Start from `backend/` with `uvicorn main:app --reload --port 8000`.
- All shop data goes through the MCP server over a persistent stdio connection. The backend has no SQL.
- CORS is open to `localhost:5173` and `localhost:3000`.
- During a run, files are written only to `output/` and `data/`.

| Route | What it does |
|---|---|
| `GET /tickets` | Every ticket with status, pending-approval count and amount, and whether a run is active |
| `POST /tickets/{id}/run` | Starts the team on a ticket in the background and returns a `run_id` (202). Returns 409 if the ticket is already running or resolved. |
| `GET /runs/{run_id}` | Run status, Boss's decision, and token usage (persisted in `output/runs.json`) |
| `GET /events?since=&ticket_id=&run_id=&limit=` | Audit-trail events, newest first, for polling |
| `GET /tickets/{id}/summary` | Per-agent summary of a ticket's latest run (conclusion, tools, handoffs, tokens), built from the audit trail |
| `GET /approvals` | Pending payment and PO requests (ticket, payee, amount, reason, requesting agent), plus balance and cash after pending |
| `POST /approvals/{id}/approve` `{"approved_by"}` | The **only** route that moves cash, via `execute_payment`. Refusals return 400. |
| `POST /approvals/{id}/reject` `{"approved_by","reason"}` | Rejects via `reject_request`. No cash moves. |
| `GET /cash` | Shop date, checking balance, payments made, total paid, and pending total |
| `POST /reset` | Recopies the original DB (same logic as `reset_db.py`). Returns 409 during a run. Adds a `database_reset` marker to the audit trail instead of wiping it. |
| `GET /health` | Liveness check and active runs |

**How a ticket becomes resolved:**
1. The backend sets the ticket to `in_progress` when the run starts.
2. Boss sets it to `resolved` after its final call, and the backend enforces this if Boss didn't.
3. Requests still pending stay on `/approvals`, and the board shows an "approval pending" badge until a human signs or voids them.

## 5. Dashboard

`frontend/` is React, Vite, and TypeScript. It reads `VITE_API_URL` (default `http://localhost:8000`) and polls `/events` every 1.5s during a run.
- **Board:** ticket slips with a RESOLVED stamp, five color-coded staff cards with handoff arrows, and a live shop-floor feed with tool chips.
- **Shift report:** per-agent summaries after each run.
- **Money:** pending approvals as checks you sign (confirm first, disabled when cash is short), a cash-register balance that counts down, and a reset button.

Layout, visual choices, and rationale are in **`output/design.md`**.

## 6. Safety rules

**Guardrails for agents that touch customers and money:**
- **A human approves every dollar.** Agents can only create *pending* requests. `execute_payment` is the only code path that moves cash. No agent is given it (`AgentSpec` raises an error if a human-only tool is ever assigned), and it refuses agent or system names as approver.
- **No negative cash.** `request_payment`, `request_purchase_order`, and `execute_payment` all check the balance, and the final `UPDATE` is guarded with `balance >= amount`. No revenue is ever assumed.
- **Vendor block.** No PO is requested or executed while the vendor has an open invoice.
- **Least privilege.** Each agent sees only its own tools, and the backend's own MCP client is the only holder of the human-only tools.
- **No outbound contact.** There is no email or vendor tool. Drafts are stored as `draft_not_sent`.
- **No invented data.** Tools return `found: false` instead of guessing, and the prompts require "unknown" over guesses. Amounts must match what's owed exactly.
- **Audit trail.** Every model call, tool call and result, delegation, final answer, human decision, status change, and reset is appended to `output/audit_trail.json`. It's never wiped. The Portkey key is redacted, and no hidden reasoning is logged.
- **Secrets.** `PORTKEY_API_KEY` comes from the environment or a gitignored `.env`. The model name lives only in `backend/config.py`.

**Token limits (`backend/config.py`):**
- Delegation depth is capped at 3 with no cycles.
- Per ticket run: **40 model requests, 60 tool calls, 250,000 total tokens**, shared across all delegated agents.
- Tool lists are scoped per agent.
- Handoffs are capped at 800 characters.
- The final run used 41,391 / 24,880 / 44,310 tokens for 101 / 102 / 103, well under the cap.
