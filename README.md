# Campus Customs Multi-Agent Operations

MGT 409 · Homework 5 · Luke

A team of AI agents runs the back counter of a small campus apparel shop. Open tickets sit on a board (a customer order, a rent notice, a bulk-discount request). The agents read and update the shop database through an **MCP server**, hand work to each other, and **request** payments and purchase orders. A **human approves every dollar** on a React dashboard.

```
React board (frontend/)  ──HTTP──▶  FastAPI backend (backend/)  ──stdio──▶  MCP server (mcp_server/)  ──▶  SQLite (data/)
      approve / reject                 PydanticAI agent team                    read + write tools           campus_customs_new.db
```

## The 5 agents
| Agent | Job | MCP tools |
|---|---|---|
| **Boss** | Reads each ticket, routes it, makes the final call (discounts never below cost), logs a note, resolves the ticket | `get_ticket`, `list_open_tickets`, `get_today`, `add_ticket_note`, `update_ticket_status` |
| **Inventory** | Stock and shortfalls; picks a restock vendor by specialty and lead time; checks if the vendor is blocked by an unpaid invoice | `check_stock`, `find_vendors`, `list_vendors`, `get_vendor_open_invoices` |
| **Accounting** | Cash against everything owed, margins, and *pending* payment and PO requests | `get_cash_balance`, `list_obligations`, `get_invoice`, `get_vendor_open_invoices`, `get_pricing`, `list_approval_requests`, `request_payment`, `request_purchase_order` |
| **Facilities** | Leases and rent | `get_lease`, `get_cash_balance`, `get_today` |
| **Customer Service** | Honest draft replies saved on the board (never sent) | `get_ticket`, `save_customer_draft` |

How delegation works:
- Any agent can delegate to any other through a `delegate` tool.
- Delegation depth is capped at 3, with no cycles.
- Each run has a per-ticket usage cap.
- **No agent can execute a payment.** Only the human approval route calls `execute_payment`.

The full reference is in [`output/harness.md`](output/harness.md).

## Run it from a fresh clone

You'll need Python 3.12+ and Node 20+.

### 1. Python setup and API key
```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
# then edit .env and set PORTKEY_API_KEY=<your key>
```

### 2. Database: copy the original to the working copy for a clean run
`data/campus_customs.db` is the original, and it's never modified. Everything runs against `data/campus_customs_new.db`.
```bash
python reset_db.py
# or, equivalently:
cp data/campus_customs.db data/campus_customs_new.db
```

### 3. MCP server (optional to start by hand)
```bash
python mcp_server/server.py      # stdio MCP server, 22 tools
```
You don't need to start it yourself to use the app. **The backend launches it automatically over stdio**, both for the agents and for its own approval and cash routes.
- `.mcp.json` registers it as a project-level MCP server at the repo root for MCP-aware coding assistants (start the assistant with the venv activated).
- `python tests/test_mcp_write_tools.py` tests every tool. It resets the working DB before and after.

### 4. Backend (FastAPI, port 8000)
```bash
cd backend && uvicorn main:app --reload --port 8000
```

### 5. Board (React + Vite, port 5173)
```bash
cd frontend && npm install && npm run dev
```
Open **http://localhost:5173**. The board calls `VITE_API_URL`, which defaults to `http://localhost:8000`.

### 6. Before a full 3-ticket run, reset
Click **↺ Reset shop** on the board, or run `python reset_db.py`. Then hand each ticket to the team and sign or void the checks that come back.

## Notes for grading
- **The working DB is committed in its end-of-run state.**
  - Checking is **$160.00**.
  - Rent ($2,400) and invoice 501 ($840) are paid, both approved by Luke.
  - All 3 tickets are resolved.

  This matches the Cash tab in `output/desk_tickets.html`. Reset it (step 6) only if you want to run the tickets again.
- **Model:** all AI calls use **gpt-6-Luna** through **Portkey**. The model name and gateway are set in one place, `backend/config.py`, and the key is read from `PORTKEY_API_KEY` (env or `.env`), never hard-coded.
- **Docs (in `output/`):**
  - `desk_tickets.html`: Expected vs Actual per ticket, Cash, and Reflection
  - `resolved_board.html`: board screenshots
  - `resolved_tickets.json`
  - `harness.md`
  - `design.md`: dashboard design
  - `mcp_smoke.json`
  - `audit_trail.json`: every agent step
  - `github_url.txt`
- **Prompt log:** `AI_prompts.md`.
