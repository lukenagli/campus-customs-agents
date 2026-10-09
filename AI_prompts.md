# AI Prompt Log: Campus Customs Multi-Agent Operations

**Course:** MGT 409, AI Foundation for Managers
**Assignment:** Homework 5, Campus Customs Multi-Agent Operations
**Name:** Luke

This file logs, word for word, the prompts I gave my AI coding assistant during this assignment, grouped by problem.

---

## Problem 1: Vibe Coder Prompt Log

### Prompt(s)

````text
I'm starting Homework 5 for my MGT 409 class. I'll give you the background for the whole project now, but we're going to build it one problem at a time. Don't write any app code until I give you each problem.

THE PROJECT
The project is called "Campus Customs Multi-Agent Operations." It's a team of AI agents that runs a small custom apparel shop. Open tickets sit on a board: customer orders, rent, unpaid bills, discount requests, etc. Over the course of this homework we'll build 3 connected pieces:
1. An MCP server that exposes tools to read and update the shop database
2. A FastAPI backend that runs a multi-agent team
3. A React dashboard where a human can watch the agents work and approve requests

The agents are:
- Boss: reads each ticket, decides who handles it, makes final calls
- Inventory: checks stock by SKU and size, flags shortfalls, figures out which vendor can restock
- Accounting: watches cash and invoices, checks margins, prepares payments or purchase orders for human approval
- Facilities: handles the shop space side (leases, rent)
- Customer Service: drafts messages to customers
Any agent can hand off work to any other agent.

SHOP RULES (keep these in mind for every problem going forward)
- The date_today field in the desk table is "today" for the shop. Use it to decide what's overdue, never the real system date.
- Vendor lead times come from the vendors table.
- A vendor won't ship new product if they have an open unpaid invoice.
- Every payment needs human approval. No exceptions. When a payment goes through, update the relevant tables (payments, cash_accounts, invoices/leases as appropriate).
- If there isn't enough cash, the pay tool has to refuse. Balances can never go negative.
- Cash only goes out. There's no revenue in this model.
- No real emails to customers and no real vendor calls. Drafts stay on the board.
- All AI calls go through Portkey using my PORTKEY_API_KEY environment variable, and every agent uses only the model gpt-6-Luna. No other model name should appear anywhere in the code.
- Final submission is a public GitHub repo, so never hardcode my API key. Read it from the environment and gitignore any .env file.

SETUP FOR NOW
1. I've added data.zip to the project folder. Unzip it so we have data/campus_customs.db. This is the original database. Never modify it.
2. Make a working copy called data/campus_customs_new.db. Everything we build later (MCP server and backend) should point at this copy, not the original.
3. Write a small reset script (e.g., reset_db.py) that overwrites campus_customs_new.db with a fresh copy of the original, so I can reset before a full run.
4. Open the database and give me a short summary of each table and what's in it, including date_today, the open tickets, the cash balance, and any open invoices, so I understand the starting state.

PROBLEM 1: VIBE CODER PROMPT LOG
Create AI_prompts.md in the project root. It's my log of what I type to you during this assignment. Set it up like this:
- A short header at the top (assignment name, my name: Luke)
- One section per problem, using "## Problem N: Title"
- Under each section, these subsections: "Prompt(s)" (what I typed, copied word for word), and "Follow-up prompt(s)", each with one sentence on what was missing after the first prompt
- Fill in the Problem 1 section now and paste this exact message in as the first prompt
- Going forward, after every prompt I give you, add it word for word to the right problem section. If it's a follow-up, add a one-sentence note on what was missing. Don't summarize or reword my prompts.

When you're done, show me the folder structure and the contents of AI_prompts.md.
````

### Follow-up prompt(s)

_None._

---

## Problem 2: Study the Campus Customs Database

### Prompt(s)

````text
Problem 2: Study the Campus Customs database.

Go through data/campus_customs.db table by table and look at every field. Read it only. Don't change anything in the original.

1. Make sure data/campus_customs_new.db exists and still matches the original. If it's missing or anything is different, run the reset script to recopy it.

2. Look closely at the 3 open tickets. For each one, follow every link to the other tables (SKU/size to inventory and pricing, invoice_id to invoices to vendors, lease_id to leases) and tell me:
   - What the ticket is asking for
   - What the data shows, with the actual numbers (stock on hand, prices, amounts, due dates)
   - Anything that's overdue or blocked, judged against date_today in the desk table, not the real date
   - Which agents would need to get involved, and which shop rules apply
   Also tell me how the tickets affect each other, like whether paying one bill changes what we can do on another, and whether the cash balance can cover everything.

3. Create output/harness.md. This is a reference doc for the agents that we'll keep adding to in later problems. For now it should have:
   - A short intro saying what the shop is and that "today" is date_today from the desk table
   - A section for each table: its fields with types, plus one short line on why that table matters to the agents and which agent uses it most
   - A short "Open tickets" section summarizing the 3 tickets and how they connect to the other tables

Keep harness.md tight. It's going to grow, so don't pad it.

Then add this prompt word for word to AI_prompts.md under "## Problem 2: Study the Campus Customs Database".
````

### Follow-up prompt(s)

_None._

---

## Problem 3: Build the MCP Server

### Prompt(s)

````text
Problem 3: Build the MCP server.

Create an MCP server in mcp_server/ using FastMCP. It should only connect to data/campus_customs_new.db, never the original. Build the database path from the file's own location so it works no matter which folder I run it from. You don't need to hook it up to anything or run it as a server yet.

For now, write these 3 tools, one for each open ticket. All 3 only read data. Don't add anything that pays, updates, or writes to the database yet. Those come later with human approval.

1. get_invoice(invoice_id): ticket 101
   Reads invoices joined to vendors. Returns the amount, due date, status, description, vendor name, vendor specialty, and vendor lead time. Using date_today from the desk table, also return whether it's overdue and by how many days. Ticket 101 is blocked because the vendor won't restock while this invoice is unpaid.

2. get_lease(lease_id): ticket 102
   Reads leases. Returns the space, landlord, monthly rent, and next due date, plus how many days until it's due (or how overdue it is), based on date_today.

3. check_stock(sku, size, qty_needed optional): ticket 103
   Reads inventory. Returns the item name, quantity on hand, and location. If qty_needed is given, also return the shortfall (needed minus on hand, never below 0). Ticket 103 needs 20 and we need to know how many are missing.

Rules for every tool:
- Use only what's in the database. Never guess or fill in data. If an ID, SKU, or size doesn't exist, return a clear "not found" message instead of making something up.
- "Today" always comes from desk.date_today, never the system clock.
- Use parameterized SQL queries.
- Give each tool a clear docstring, since the agents will read it to decide when to use the tool.

Then:
- Add mcp_server/README.md: what the server is for, that it uses data/campus_customs_new.db, a list of the 3 tools, and how to run it.
- Add fastmcp to requirements.txt.
- In output/harness.md, add an "MCP Tools" section. For each tool, list: the tool name and inputs, which table(s) it reads, which ticket it unlocks (101, 102, or 103), and one sentence on why it's the right tool for that ticket, using the actual numbers from the data. No vague lines like "reads inventory."
- Test all 3 tools against the working copy (FastMCP's in-memory Client is fine) using the real ticket inputs, plus one bad input, and show me the results.
- Add this prompt word for word to AI_prompts.md under "## Problem 3: Build the MCP Server".
````

### Follow-up prompt(s)

_None._

---

## Problem 4: Add the MCP Server to Vibe Coder and Test Each Tool

### Prompt(s)

````text
Problem 4: Connect the MCP server to Claude Code and test each tool.

Set up the MCP server from Problem 3 so you can call its tools directly in this project. Create a .mcp.json file in the project root that registers it at the project level, named "campus-customs". Point it at the Python interpreter that actually has fastmcp installed (use the venv's Python if there is one) and at the server file in mcp_server/. Don't change any of the tool code.

Show me the final .mcp.json, and tell me what I need to do to get you to load it (restart, approve, etc.).

Add this prompt word for word to AI_prompts.md under "## Problem 4: Add the MCP Server to Vibe Coder and Test Each Tool".
````

### Follow-up prompt(s)

````text
Using only the campus-customs MCP tools, is invoice 501 overdue? Who is the vendor and how much do we owe?
````

What was missing: the first prompt only registered the server, so this follow-up actually tests `get_invoice` through the connected MCP tools.

````text
I want to stay in this chat. Two things:

1. Move everything for HW 5 into Homework/HW 5. Check where every file we've created actually lives (data/, mcp_server/, output/, AI_prompts.md, requirements.txt, the reset script, .mcp.json, any venv). Move anything that's outside HW 5 into it, keeping the same structure, and fix any paths that break. Don't touch any other course files. Show me the final HW 5 folder tree. From now on, treat Homework/HW 5 as the project root for every path in every problem.

2. Get the campus-customs MCP tools working in this chat. Keep HW 5/.mcp.json as is, since that's the one that gets submitted. Since this session started in the parent folder, add whatever config this session needs, pointing at the server in HW 5 with paths that work from here (for example, a .mcp.json in the folder this session started in, or `claude mcp add` at local scope). Then tell me exactly what I need to do to load it without losing this conversation. If there's truly no way to do that without a new session, tell me straight.
````

What was missing: the first prompt didn't account for this chat having started in the parent folder, so its MCP tools couldn't load here and the project root needed to be pinned to Homework/HW 5.

````text
Using only the campus-customs MCP tools, is invoice 501 overdue? Who is the vendor and how much do we owe?
````

What was missing: the MCP tools weren't loaded the first time I asked this, so I re-asked after reopening the session to actually test `get_invoice` through the connected server.

````text
Using only the campus-customs MCP tools, when is rent due on lease 1 and how much is it?
````

What was missing: the earlier test only covered `get_invoice`, so this one tests `get_lease` for ticket 102.

````text
Using only the campus-customs MCP tools, do we have enough navy hoodies in size M for an order of 20?
````

What was missing: `check_stock` hadn't been tested yet, so this one covers ticket 103 and completes the test of all three tools.

````text
Now create output/mcp_smoke.json with one entry for each of the 3 MCP tool calls you just made. Each entry should have: "prompt" (exactly what I asked you), "tool" (the full MCP tool name you called), "arguments" (what you passed it), and "output" (the raw tool response, copied exactly, not summarized).

Then check each output against data/campus_customs_new.db with a direct SQL query and add a "verified_against_db": true/false field to each entry. Tell me if anything doesn't match.

Add this prompt, plus my 3 test questions, word for word to the Problem 4 section of AI_prompts.md.
````

What was missing: the tool test answers were only in the chat, so this saves them as a record (output/mcp_smoke.json) and checks them against the database.

---

## Problem 5: Build the Agent Team and Grow the MCP Tools

### Prompt(s)

````text
Problem 5: Build the agent team and add the MCP tools they need. We'll do this in two parts. Part A is just the MCP tools. Don't build any agents yet.

Add the tools the agents need to resolve all 3 tickets to mcp_server/. Keep the existing 3 tools. Same rules as before: only data from the database, "today" comes from desk.date_today, parameterized SQL, a clear docstring on each tool, and only data/campus_customs_new.db.

Read tools to add (adjust if you think something's missing):
- get_today: the date_today from the desk table
- list_open_tickets / get_ticket(ticket_id)
- get_pricing(sku): unit cost, list price, and margin. Add an optional proposed_price that returns the margin at that price, so Accounting can check a discount
- list_vendors / find_vendors(specialty): includes lead_days
- get_vendor_open_invoices(vendor_id): so Inventory can tell whether a vendor is blocked from shipping
- get_cash_balance

Write tools for agents (keep them safe):
- add_ticket_note(ticket_id, author, note) and update_ticket_status(ticket_id, status): used by Boss
- save_customer_draft(ticket_id, draft): stores Customer Service's message on the ticket board. It never sends anything.
- request_payment(kind, ref_id, amount, reason, requested_by): for an invoice or rent. This must NOT move money. It only creates a pending request for a human to approve. Store these in an approval_requests table that the server creates if it doesn't exist (so resetting the database clears them).
- request_purchase_order(vendor_id, sku, size, qty, reason, requested_by): also just a pending request. It should refuse if the vendor has an open unpaid invoice.

Human-only tool:
- execute_payment(request_id, approved_by): the only tool that moves money. It must check that the request is pending and that approved_by is a human name (not an agent's), and refuse if there isn't enough cash, because the balance can never go negative. In one transaction it should: insert a row into payments (paid_at = date_today, account = checking), lower the cash_accounts balance, mark the invoice paid or move the lease's next_due ahead one month, and mark the request executed. No agent will ever get access to this tool. Only the backend's human-approval step (built in a later problem) calls it.

Test the new tools against the working copy, including these cases: execute_payment refusing a payment larger than the cash balance, refusing an agent name as approved_by, and refusing a purchase order to Bulldog Print while invoice 501 is open. Run the reset script afterward so the database is clean.

Update mcp_server/README.md so the tool list matches what's there now.

Add this prompt word for word to AI_prompts.md under "## Problem 5: Build the Agent Team and Grow the MCP Tools".
````

### Follow-up prompt(s)

````text
Part B of Problem 5: Now build the agent team with PydanticAI in backend/.

MODEL
- Every agent uses gpt-6-Luna through Portkey, with the key read from the PORTKEY_API_KEY environment variable. Set up the Portkey connection the same way my earlier homeworks did if you can find one. Otherwise ask me before guessing.
- Put the model name and Portkey setup in one config file. "gpt-6-Luna" should appear exactly once in the codebase, and no other model name (no gpt-4o, no claude, no PydanticAI default) should appear anywhere. When you're done, grep the whole project to prove it.

STRUCTURE
- backend/prompts/: one system prompt file per agent (boss.md, inventory.md, accounting.md, facilities.md, customer_service.md)
- backend/models.py: Pydantic data types (ticket decisions, delegation requests and results, payment and PO requests, customer drafts, audit entries)
- backend/agents/: one file per agent, plus a shared module that loads prompts and wires everything together

TOOLS
All shop data has to come from the MCP server through PydanticAI's MCP support. Don't write any direct SQL or a second shop-tools layer in the backend. Give each agent only the MCP tools it actually needs:
- Boss: tickets, notes, status, today
- Inventory: stock, vendors, vendor open invoices
- Accounting: cash, invoices, pricing, request_payment, request_purchase_order
- Facilities: leases, cash, today
- Customer Service: get_ticket, save_customer_draft
No agent gets execute_payment.

DELEGATION (full connectivity)
Every agent gets a delegate tool that can hand a task to any of the other 4 agents and get the answer back. To keep that from looping forever and burning tokens:
- Max delegation depth of 3
- Pass a short task description, not the whole chat history
- Share usage tracking across delegations
- Set a PydanticAI UsageLimits cap per ticket run (requests and total tokens)
Put these limits in the config file.

AGENT PROMPTS
Write detailed prompts. Each one needs: the agent's role and scope, what it should hand off and to whom, the shop rules that apply to it, the tools it has, what its output should look like, and what it must never do. Rules to work in where they apply:
- "Today" is date_today from the desk table.
- Lead times come from the vendors table.
- A vendor won't ship while it has an open unpaid invoice.
- Every payment needs human approval. Agents can only request payments.
- No negative cash balance.
- No money comes in.
- Never contact customers or vendors. Drafts stay on the board.
- Never invent data. If something isn't in the tools, say so.
Role-specific points:
- Boss: routes each ticket, makes final calls (including whether to approve a discount, never below unit cost), and closes or updates tickets
- Inventory: checks stock and shortfall, then picks a vendor by specialty and lead time and checks that vendor isn't blocked
- Accounting: checks cash against everything owed before recommending payments, puts the most urgent or overdue items first, and checks margin on any discount
- Facilities: handles rent and leases and works with Accounting to request rent payment
- Customer Service: writes honest drafts that never promise dates or prices the data doesn't support

AUDIT TRAIL
As agents run, append to output/audit_trail.json. Never wipe it; read, append, and write back as a valid JSON array. Log one entry per loop step with: timestamp, run_id, ticket_id, agent, step type (model call, tool call, tool result, delegation sent/returned, final answer), tool name and arguments, a short result, delegation depth, and token usage. Never log the API key.

HARNESS
Update output/harness.md with:
- An "Agents" section: each agent's role, its MCP tools, and who it usually delegates to
- An updated "MCP Tools" section listing every tool and the table(s) it uses
- A short "Safety" section: guardrails a real business would want when agents handle real customers and money (human approval, least-privilege tools, no outbound messages, audit trail, no invented data, cash checks), plus the token limits (depth cap, usage limits, scoped tools, short handoffs)

TEST
Reset the database, run just ticket 102 once to prove the wiring works, show me the audit trail entries, then reset again. Don't run all 3 tickets yet.

Add this prompt word for word to AI_prompts.md under Problem 5 as a follow-up, with this note on what was missing: "Part A only covered the MCP tools; the agents, delegation, audit trail and harness still needed to be built."
````

What was missing: Part A only covered the MCP tools; the agents, delegation, audit trail and harness still needed to be built.

---

## Problem 6: Plan the Three Tickets

### Prompt(s)

````text
Problem 6: Plan the 3 tickets before we wire up the backend.

Build output/desk_tickets.html as a single self-contained page I can open by double-clicking. Inline CSS and JS only, no CDNs or external files. Make it clean and readable.

Tabs: Ticket 101 | Ticket 102 | Ticket 103 | Cash | Reflection
- Each ticket tab: a short header with the ticket facts (requester, ask, key numbers), an "Expected" section filled with my plan below, and an empty "Actual" section that says "Filled in after the agent run (Problem 7+)"
- In each Expected section, add a simple delegation flow diagram (inline SVG or CSS boxes and arrows) showing the order of handoffs, plus a list of "Not involved" agents
- Cash and Reflection tabs: just say "Coming in a later problem"

Use the exact MCP tool names from mcp_server/. If a name I use below doesn't match, use the real one and tell me what you changed. Keep my wording; only fix the tool names.

TICKET 101: Bulldog tee, size S, qty 1 (Tauhid Zaman)
Boss calls first: Inventory, because it's a customer order and the first question is whether we even have the shirt.
Expected delegations:
1. Boss → Inventory: check stock on CC-TEE-WHITE size S. It'll come back 0. Inventory looks up the apparel vendor (Bulldog Print, 5-day lead time) and finds they're blocked by open invoice 501.
2. Inventory → Accounting: the restock vendor is blocked by an unpaid invoice. Accounting confirms invoice 501 is $840, 3 days overdue, checks the cash balance ($3,400), and requests payment for human approval. The restock PO waits until the invoice is paid.
3. Boss → Customer Service: draft a message to Tauhid saying size S is out of stock and a restock is in progress, with no promised date until the vendor is paid and confirms.
4. Boss: logs a note and sets the ticket to waiting on approval.
Not involved: Facilities.
Expected MCP tools: get_ticket, check_stock, find_vendors, get_vendor_open_invoices, get_invoice, get_cash_balance, request_payment, save_customer_draft, add_ticket_note, update_ticket_status

TICKET 102: Rent due (Elm City Properties)
Boss calls first: Facilities, because rent and the lease are its job.
Expected delegations:
1. Boss → Facilities: pull lease 1. Rent is $2,400, due 9/2, 2 days from today (8/31), so it isn't overdue yet.
2. Facilities → Accounting: request the rent payment. Accounting checks cash against everything we owe, not just rent: $2,400 rent + $840 invoice = $3,240, leaving only $160 of the $3,400. Both bills can be covered, and Accounting requests the $2,400 payment for human approval.
3. Boss: logs a note and sets the ticket to waiting on approval.
Not involved: Inventory, Customer Service (the landlord isn't a customer and we don't contact vendors or landlords).
Expected MCP tools: get_ticket, get_lease, get_today, get_cash_balance, get_invoice, request_payment, add_ticket_note, update_ticket_status

TICKET 103: Bulk hoodie discount, 20 navy hoodies size M (Yale AI Club)
Boss calls first: Inventory, because if we can't fill the order, the discount question doesn't matter yet.
Expected delegations:
1. Boss → Inventory: check CC-HOOD-NAVY size M for 20. We only have 8, so we're 12 short. Restocking goes through Bulldog Print (5 days), which is blocked by invoice 501.
2. Boss → Accounting: check margin on a bulk discount. Cost is $22 and list is $58, so there's room, but never price below cost. Also flag that restocking 12 hoodies costs about $264 at unit cost, more than the $160 we'd have left after paying rent and invoice 501. We can't afford the full restock if both bills get paid.
3. Boss makes the final call on the discount and on how much of the order we can promise.
4. Boss → Customer Service: draft a reply to Yale AI Club offering what we can actually back up (8 now, the rest dependent on restock, and the approved discount), with no promised delivery date.
5. Boss: logs a note and updates the status.
Not involved: Facilities.
Expected MCP tools: get_ticket, check_stock, find_vendors, get_vendor_open_invoices, get_pricing, get_cash_balance, save_customer_draft, add_ticket_note, update_ticket_status

When you're done, open the page in a headless browser and confirm every tab switches correctly.

Add this prompt word for word to AI_prompts.md under "## Problem 6: Plan the Three Tickets".
````

### Follow-up prompt(s)

_None._

---

## Problem 7: Backend Routes

### Prompt(s)

````text
Problem 7: Build the backend routes in backend/main.py with FastAPI. The React dashboard in the next problem will call these.

ROUTES
- GET /tickets: all tickets with id, type, requester, subject, and status (open/resolved, plus any in-between status the agents set)
- POST /tickets/{id}/run: runs the agent team on one ticket. Run it in the background and return a run_id right away so the board can show progress while it works. Refuse if that ticket is already running or already resolved.
- GET /events?since=&ticket_id=&limit=: recent agent events from output/audit_trail.json (which agent, what it said, which tools it called, delegations), newest first, so the board can poll
- GET /approvals: pending payment and purchase order requests, with the ticket they belong to, the amount, the reason, and the agent that asked
- POST /approvals/{id}/approve with body {"approved_by": "<human name>"}: the ONLY route that moves cash. It has to go through the MCP server's execute_payment tool. No direct SQL in the backend.
- POST /approvals/{id}/reject with body {"approved_by", "reason"}: marks the request rejected. No cash moves.
- GET /cash: current checking balance from cash_accounts, plus a list of payments made so far
- POST /reset: copies data/campus_customs.db over data/campus_customs_new.db (reuse the reset script logic). Don't wipe audit_trail.json. Add a "database reset" marker event to it instead.

PURCHASE ORDERS
Approving a purchase order should also move cash. The amount is qty × unit_cost from pricing. Update the MCP tools so request_purchase_order calculates and stores that amount, and execute_payment handles both payments and POs. Both must still refuse when there isn't enough cash, and a PO must still refuse when the vendor has an open unpaid invoice. Don't add stock when a PO is approved, since goods arrive after the vendor's lead time. Make sure every approval request has a ticket_id.

After an approval goes through, add a note to the linked ticket. Then explain how a ticket actually ends up "resolved" (Boss at the end of a run, or after the last approval clears) so the board status makes sense.

SETUP DETAILS
- I'll start it from inside backend/ with: uvicorn main:app --reload --port 8000. Build every path (data/, output/, mcp_server/) from the file's own location so they work from there.
- Load PORTKEY_API_KEY from the environment or a gitignored .env. Never hardcode it.
- Don't write any files inside backend/ during a run, or --reload will restart the server in the middle of a run.
- Turn on CORS for the local React dev server (localhost:5173 and localhost:3000).
- Add fastapi and uvicorn to requirements.txt.

TEST
Start the server and hit every route with curl:
- Reset, then run ticket 102 only, then show the pending approval
- Reject approving it with an agent name as approved_by
- Approve it with "Luke"
- Show /cash: it should drop from $3,400 to $1,000, with one payment row
- Reset, and confirm cash is back to $3,400 and the payments table is empty
Don't run all 3 tickets yet.

Then add a "Backend Routes" section to output/harness.md with one line per route (method + URL: what it does), and add this prompt word for word to AI_prompts.md under "## Problem 7: Backend Routes".
````

### Follow-up prompt(s)

_None._

---

## Problem 8: Agent Dashboard

### Prompt(s)

````text
Problem 8: Build the agent dashboard in frontend/ using React + Vite + TypeScript. It calls the backend routes from Problem 7 at http://localhost:8000. Put that URL in one config value (VITE_API_URL, defaulting to localhost:8000). The backend already allows CORS from localhost:5173; confirm that's still true.

WHAT IT HAS TO DO
- List all 3 tickets with their status
- Pick a ticket and start the agent team on it
- While it runs, show each agent and what it's saying and doing live: messages, tool calls, and delegations (Boss → Inventory, etc.). Poll /events about every 1.5 seconds while a run is active.
- Mark the ticket resolved when the run finishes. If it still has pending approvals, show it as resolved with an "approval pending" badge. If the backend doesn't set resolved at the end of a run, fix that so the two match.
- After a run, show a short summary per agent for that ticket: what it did, which tools it used, and who it handed off to. If it's cleaner, add a backend route like GET /tickets/{id}/summary that builds this from the audit trail.
- Approvals panel: a human can approve or reject each pending payment or PO. Show an approver name field (default "Luke"), the amount, what it's for, and what cash would be after. Confirm before approving. Disable approve and explain why if cash is too low. Show any refusal from the backend clearly.
- Show the checking balance. It should visibly drop after an approved payment.
- A reset button (with a confirm) that calls /reset

DESIGN DIRECTION
Make it feel like the back counter of a campus apparel shop, not a generic admin panel.
- Tickets look like paper order slips or receipts pinned to a board. When a ticket resolves, it gets a "RESOLVED" rubber-stamp animation.
- The 5 agents sit around the desk as distinct "staff" cards, each with its own color, icon, and role label. Boss feels like the manager and the others like specialists. The active agent lights up while it works, and delegation shows as a visible handoff between cards.
- The live feed reads like a shop-floor conversation, with each message tagged and colored by agent. Tool calls show as small chips with the tool name, so you can see the agent is working from real data.
- Cash looks like a cash register display. The number animates down after a payment, and next to it is a small bar showing cash against what's owed in pending approvals.
- Approvals look like checks or payment slips waiting for a signature. Approving one "signs" it.
- Yale-blue base with warm paper tones. Good contrast, readable type, and it has to hold up on a laptop screen and a narrow window.
Use your frontend-design skill if you have one. Be creative but keep it clean and usable; nobody wants a cluttered desk.

TEST
Run npm run build with no TypeScript errors. Then, with the backend running: reset, open the board in a headless browser, run ticket 102 from the UI, approve the rent as "Luke", and confirm cash goes from $3,400 to $1,000. Take screenshots before, during, and after the run (and one at narrow width) and show them to me. Reset again at the end. Don't run 101 or 103 yet.

DOCS
- Write output/design.md: the layout, how each agent looks different, how resolved tickets, approvals, and cash are shown, and why I made each choice, including the creative touches that make it feel like a real desk people would enjoy using. Keep it short and specific.
- Make sure frontend/node_modules is gitignored.
- Add this prompt word for word to AI_prompts.md under "## Problem 8: Agent Dashboard".
````

### Follow-up prompt(s)

_None._

---

## Problem 9: Resolve the Tickets

### Prompt(s)

````text
Problem 9: Resolve the tickets. First, setup only.

Start the backend (uvicorn on port 8000 from backend/) and the frontend (npm run dev) in the background, and tell me the board URL. Reset the database through the /reset route. Then confirm with a direct query that data/campus_customs_new.db matches the original: checking balance $3,400, payments table empty, invoice 501 open, all 3 tickets open, and no approval requests. Tell me the starting balance.

Do NOT run any tickets. I'm going to run all 3 from the board myself and do the approvals as the human.

Add this prompt word for word to AI_prompts.md under "## Problem 9: Resolve the Tickets".
````

### Follow-up prompt(s)

````text
All 3 tickets are resolved on the board. Now document this run. Use only the events after the most recent "database reset" marker in output/audit_trail.json, and get every number from the working database, not from memory.

1. output/desk_tickets.html, each ticket tab: fill in the Actual section from the audit trail with which agents worked, every delegation in order, and every MCP tool called. Use the same flow-diagram style as Expected. Don't change my Expected section. Add a short "Expected vs Actual" line listing real differences (agents or tools I expected that didn't show up, extra ones, a different first call). Be honest; don't make Actual match Expected.

2. The Cash tab in the same file: an itemized table with the starting balance ($3,400 after reset), then one row per ticket showing the cash change when it resolved, the reason (which payment or PO, request id, amount, approved by), and the running balance. Include any refused or rejected requests at $0 with the reason. End with the ending balance. Build this from the payments and approval_requests tables, and prove it with a check: starting balance minus the sum of payments equals cash_accounts.balance. Show me that query and its result.

3. output/resolved_tickets.json: for each ticket, the id, final status, a 1-2 sentence outcome, what each agent that worked on it contributed, and the human approvals (request id, amount, approved by, approved or rejected).

4. output/resolved_board.html: use a headless browser on the live board to screenshot each resolved ticket (101, 102, 103) with its agent summary showing, and one of the cash display. Embed the images as base64 so the page works when double-clicked with no other files. Add a caption under each.

5. Finish output/harness.md so it covers, in this order: tables, MCP tools (with tables used), the 5 agents, API routes, the dashboard (point to design.md), and the safety rules. Make it consistent with what the code actually does now.

Don't reset the database. It needs to stay at the end-of-run state for grading.
````

What was missing: the first Problem 9 prompt was setup only; the run still had to be documented from the audit trail and the database (Actual sections, Cash tab, resolved_tickets.json, resolved_board.html, and the finished harness).

---

## Problem 10: Reflection

### Prompt(s)

````text
Problem 10: Reflection. Fill in the Reflection tab of output/desk_tickets.html. Base everything on the final run (events after the last reset marker in output/audit_trail.json), the ticket tabs, the Cash tab, and the current database. Every claim needs a real Campus Customs detail behind it (ticket numbers, dollar amounts, agent names, tool names, counts from the audit trail). No generic AI talk.

Write it in first person, in a casual but sharp MBA-student voice, like I'm explaining to a classmate what actually happened. Be detailed and thorough. Use short headers and some bullets, but mostly real sentences. After any claim with a number in it, add a short evidence pointer (e.g., "see Cash tab," "Ticket 103 → Actual").

Before writing, pull these numbers from the audit trail for each ticket: agents involved (expected vs actual), delegations, model calls, MCP tool calls, tokens, and run time. Put them in a small table at the top of the Reflection tab.

SECTION 1: How did the agents do on each ticket, and how did Actual compare to Expected?
For each of 101, 102, and 103, grade the run on four things and give a letter grade with reasons:
- Correctness: right numbers, shop rules followed (overdue judged by date_today, vendor block from invoice 501, no negative cash)
- Efficiency: handoffs, tool calls, and tokens compared with my Expected plan; call out any unnecessary handoffs or extra agents
- Safety: no cash moved without my approval; any refused requests
- Customer draft quality (101 and 103): honest, no promised dates or prices the data doesn't support
Then compare directly to my Expected plan: who Boss called first, which delegations matched, which agents or tools were extra or missing, and why I think that happened. Say plainly whether Accounting caught the cash squeeze on its own (paying rent + invoice 501 leaves $160, and restocking 12 hoodies costs about $264) or missed it. Be honest about mistakes; don't make it sound better than it was.

SECTION 2: What would have been simpler as one agent with tools, and why?
Use ticket 102 as the main example: get_lease, get_cash_balance, and request_payment could be done by one agent in a few calls, so compare the real handoff and token count to that. Make the bigger point too: one agent sees every obligation at once, while the multi-agent setup only catches the cash squeeze if someone hands Accounting the full picture. Then give the honest counterargument with specifics from this app: only Accounting can request payments, nobody can execute them, and the audit trail shows who did what. End with a clear opinion on where multiple agents earn their cost and where they don't.

SECTION 3: Three new problems this team CAN solve with the tools I built
For each one: the scenario, which agents handle it, the exact MCP tools they'd call, and what the result would be using real database values. Use these unless the data says otherwise:
1. Crest Mug restock: CC-MUG-CREST has 0 in stock. Elm City Gifts sells mugs, has no open invoice, and has a 3-day lead time, so the team can request a PO at $3.50 each, which needs my approval.
2. A customer order for Yale Caps (CC-HAT-BLUE, 40 in stock): a stock check plus a Customer Service draft, with no money involved.
3. Next month's rent, due 2026-10-02: the team finds it and requests $2,400, and the pay tool refuses because cash is too low. The system works as designed and correctly surfaces a real problem.

SECTION 4: Three new problems this team CANNOT solve, and what tools and agents it would need
For each one: why the current tools fall short (name the missing piece), then the specific new tools, tables, and agents I'd add, and how approval and safety would work:
1. A cash crunch with no way to bring money in: the shop is down to about $160 and we didn't model revenue. Needs a sales table, record_sale and forecast_cash tools, and a Treasury/Forecasting agent.
2. Actually filling orders: there's no way to reserve the 8 hoodies for Yale AI Club, take stock out when an order ships, receive a PO once the lead time passes, or move date_today forward. Needs reserve_stock, adjust_inventory, receive_shipment, an orders table, and an advance_day tool, with Inventory getting write access gated by approval.
3. Negotiating with outside parties: a payment plan with Bulldog Print or a rent extension from Elm City Properties. Today we can only draft. Needs send_message with a human approval gate before anything goes out, partial-payment support in the pay tool, and a Vendor Relations agent.

Check every number against the database and audit trail before writing it. If my run differs from anything I described above (for example, the hoodie PO was never requested, or the ending cash isn't $160), go with what the data shows and tell me what you changed.

Then add this prompt word for word to AI_prompts.md under "## Problem 10: Reflection".
````

### Follow-up prompt(s)

_None._

---

## Problem 11: Submit to GitHub

### Prompt(s)

````text
Problem 11: Submit to GitHub. The repo needs to match this layout at the root (extra helper files like the reset script or backend/agents/ are fine):

AI_prompts.md, requirements.txt, .env.example, .gitignore, .mcp.json, README.md, data/ (campus_customs.db AND campus_customs_new.db), mcp_server/ (server.py, README.md), frontend/, backend/ (main.py, models.py, prompts/ with boss.md, inventory.md, accounting.md, facilities.md, customer_service.md), output/ (harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt)

Do these in order:

1. Add this prompt word for word to AI_prompts.md under "## Problem 11: Submit to GitHub". Then review the whole AI_prompts.md: there should be one section for each of Problems 1-11, each with the number and title, at least one prompt, and any follow-ups with a one-sentence note on what was missing. Tell me if anything's missing. Don't invent prompts I didn't send.

2. README.md at the root: a short overview of the project and the 5 agents, then setup steps a grader can follow from a fresh clone:
   - Python setup (venv, pip install -r requirements.txt), and copy .env.example to .env and add a PORTKEY_API_KEY
   - Copy the original DB to the working copy for a clean run (show the reset script and the cp command)
   - Start the MCP server (and explain that the backend also launches it automatically over stdio)
   - Start the backend: cd backend && uvicorn main:app --reload --port 8000
   - Start the board: cd frontend && npm install && npm run dev (http://localhost:5173)
   - Reset the DB before a full 3-ticket run, using the board's reset button or the reset script
   - A note that the working DB in the repo is left in its end-of-run state (checking $160) so it matches the Cash tab, and that all AI calls use gpt-6-Luna through Portkey

3. .env.example with just PORTKEY_API_KEY= (no value). .gitignore must exclude .env, venv/.venv, __pycache__, frontend/node_modules, frontend/dist, and .DS_Store. It must NOT exclude the .db files.

4. Make .mcp.json portable: no absolute paths or paths to my own computer or venv. It should work from a fresh clone at the repo root.

5. Security and rules check before anything gets pushed. Show me the results:
   - Search every file that will be committed for my actual Portkey key, anything that looks like an API key, and any .env file. There should be zero hits.
   - Search for model names: "gpt-6-Luna" can appear in code only in the one config spot, and there should be no other model name anywhere (gpt-4, gpt-4o, claude, etc.)
   - Confirm data/campus_customs.db is unchanged from the original download and data/campus_customs_new.db shows checking at $160. Don't reset it.

6. Initialize git if needed, then create a PUBLIC GitHub repo named campus-customs-agents using the gh CLI (if gh isn't logged in, stop and tell me how to log in). Write the repo URL into output/github_url.txt, commit everything, and push. Before committing, show me the list of staged files so I can confirm .env and node_modules aren't in it.

7. Test it: clone the repo fresh into a temp folder, confirm the file tree matches the layout above, that both .db files are present, that there's no .env, and that npm run build works in the frontend. Then give me the final repo URL to submit on Canvas.
````

### Follow-up prompt(s)

_None._
