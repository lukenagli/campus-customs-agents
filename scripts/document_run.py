"""Document the final run from the audit trail and the working database.

Uses ONLY events after the most recent "database_reset" marker in
output/audit_trail.json, and reads every number from the databases
(read-only). Never writes to either database.

Writes:
- output/desk_tickets.html: Actual section of each ticket tab, the Cash tab,
  and the metrics table at the top of the Reflection tab (between markers;
  the Expected sections are never touched)
- output/resolved_tickets.json

Usage:
    python scripts/document_run.py
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "output" / "audit_trail.json"
RUNS = ROOT / "output" / "runs.json"
DESK = ROOT / "output" / "desk_tickets.html"
RESOLVED = ROOT / "output" / "resolved_tickets.json"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"

NAMES = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service"}
AGENT_ORDER = list(NAMES)

# The user's plan, transcribed from the Expected sections (Problem 6).
EXPECTED = {
    101: {"first": "inventory",
          "delegations": [("boss", "inventory"), ("inventory", "accounting"), ("boss", "customer_service")],
          "agents": {"boss", "inventory", "accounting", "customer_service"},
          "tools": ["get_ticket", "check_stock", "find_vendors", "get_vendor_open_invoices", "get_invoice",
                    "get_cash_balance", "request_payment", "save_customer_draft", "add_ticket_note",
                    "update_ticket_status"],
          "status": "waiting on approval"},
    102: {"first": "facilities",
          "delegations": [("boss", "facilities"), ("facilities", "accounting")],
          "agents": {"boss", "facilities", "accounting"},
          "tools": ["get_ticket", "get_lease", "get_today", "get_cash_balance", "get_invoice", "request_payment",
                    "add_ticket_note", "update_ticket_status"],
          "status": "waiting on approval"},
    103: {"first": "inventory",
          "delegations": [("boss", "inventory"), ("boss", "accounting"), ("boss", "customer_service")],
          "agents": {"boss", "inventory", "accounting", "customer_service"},
          "tools": ["get_ticket", "check_stock", "find_vendors", "get_vendor_open_invoices", "get_pricing",
                    "get_cash_balance", "save_customer_draft", "add_ticket_note", "update_ticket_status"],
          "status": "updated (unspecified)"},
}

e = html.escape


def money(x: float) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


# ---------------------------------------------------------------- load data

def load_events() -> tuple[list[dict], dict]:
    events = json.loads(AUDIT.read_text(encoding="utf-8"))
    for i, ev in enumerate(events):
        ev["id"] = i
    reset = max((ev for ev in events if ev["step_type"] == "database_reset"), key=lambda ev: ev["id"])
    return [ev for ev in events if ev["id"] > reset["id"]], reset


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"{WORKING_DB.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{ORIGINAL_DB.as_uri()}?mode=ro' AS original")
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params)]


# ---------------------------------------------------------------- per-ticket analysis

def analyze(events: list[dict], ticket_id: int) -> dict:
    starts = [ev for ev in events if ev["ticket_id"] == ticket_id and ev["step_type"] == "run_started"]
    assert len(starts) == 1, f"expected exactly one run for ticket {ticket_id} after the reset, got {len(starts)}"
    run_id = starts[0]["run_id"]
    run = [ev for ev in events if ev["run_id"] == run_id]
    agents = []
    for ev in run:
        if ev["agent"] in NAMES and ev["agent"] not in agents:
            agents.append(ev["agent"])
    delegations = [(ev["agent"], ev["tool_args"]["to_agent"], ev["tool_args"]["task"])
                   for ev in run if ev["step_type"] == "delegation_sent"]
    tool_calls = [(ev["agent"], ev["tool_name"], ev["tool_args"] or {})
                  for ev in run if ev["step_type"] == "tool_call" and ev["tool_name"] != "delegate"]
    results = [(ev["agent"], ev["tool_name"], ev["result"] or "")
               for ev in run if ev["step_type"] == "tool_result" and ev["tool_name"] != "delegate"]
    refused = [r for r in results if re.search(r'"refused": true|"found": false|"ok": false', r[2])]
    model_calls = [ev for ev in run if ev["step_type"] == "model_call"]
    tokens = sum((ev["step_usage"] or {}).get("total_tokens", 0) for ev in model_calls)
    t0 = datetime.fromisoformat(run[0]["timestamp"])
    t1 = datetime.fromisoformat(run[-1]["timestamp"])
    reports = {ev["agent"]: ev["result"] for ev in run if ev["step_type"] == "delegation_returned"}
    humans = [ev for ev in events if ev["ticket_id"] == ticket_id and ev["step_type"] == "human_decision"]
    errors = [ev for ev in run if ev["step_type"] == "error"]
    first_call = delegations[0][1] if delegations and delegations[0][0] == "boss" else None
    return {"run_id": run_id, "agents": agents, "delegations": delegations, "tool_calls": tool_calls,
            "results": results, "refused": refused, "model_calls": len(model_calls), "tokens": tokens,
            "seconds": (t1 - t0).total_seconds(), "started": run[0]["timestamp"], "reports": reports,
            "humans": humans, "errors": errors, "first_call": first_call}


def tool_result(a: dict, tool: str, agent: str | None = None) -> str:
    for ag, name, res in a["results"]:
        if name == tool and (agent is None or ag == agent):
            return res
    raise AssertionError(f"no {tool} result")


def compare(ticket_id: int, a: dict) -> list[str]:
    exp = EXPECTED[ticket_id]
    out = []
    first = a["first_call"]
    out.append(f"Boss called <b>{NAMES[first]}</b> first, "
               + ("as expected." if first == exp["first"] else f"not {NAMES[exp['first']]} as planned."))
    actual_pairs = [(f, t) for f, t, _ in a["delegations"]]
    if actual_pairs == exp["delegations"]:
        out.append("Delegations matched the plan exactly, in the same order: "
                   + ", ".join(f"{NAMES[f]} → {NAMES[t]}" for f, t in actual_pairs) + ".")
    else:
        missing = [p for p in exp["delegations"] if p not in actual_pairs]
        extra = [p for p in actual_pairs if p not in exp["delegations"]]
        if missing:
            out.append("Expected handoffs that didn't happen: " + ", ".join(f"{NAMES[f]} → {NAMES[t]}" for f, t in missing) + ".")
        if extra:
            out.append("Extra handoffs: " + ", ".join(f"{NAMES[f]} → {NAMES[t]}" for f, t in extra) + ".")
    agents = set(a["agents"])
    if agents == exp["agents"]:
        out.append("Same agents as planned; " + ", ".join(NAMES[x] for x in AGENT_ORDER if x not in agents)
                   + " not involved, as expected.")
    else:
        if exp["agents"] - agents:
            out.append("Expected agents that didn't show up: " + ", ".join(NAMES[x] for x in exp["agents"] - agents) + ".")
        if agents - exp["agents"]:
            out.append("Extra agents: " + ", ".join(NAMES[x] for x in agents - exp["agents"]) + ".")
    used = [t for _, t, _ in a["tool_calls"]]
    missing_tools = [t for t in exp["tools"] if t not in used]
    extra_tools = sorted(set(used) - set(exp["tools"]), key=used.index)
    if missing_tools:
        out.append("Expected tools never called: " + ", ".join(f"<code>{t}</code>" for t in missing_tools) + ".")
    if extra_tools:
        out.append("Extra tools: " + ", ".join(f"<code>{t}</code> ×{used.count(t)}" for t in extra_tools) + ".")
    dupes = [t for t in exp["tools"] if used.count(t) > 1]
    if dupes:
        out.append("Called more than once: " + ", ".join(f"<code>{t}</code> ×{used.count(t)}" for t in dupes) + ".")
    return out


# ---------------------------------------------------------------- facts checked against the data

def facts(conn, A: dict) -> dict[int, list[str]]:
    """Ticket-specific differences from the plan, each asserted against the audit trail / DB."""
    f: dict[int, list[str]] = {101: [], 102: [], 103: []}
    status = {r["id"]: r["status"] for r in rows(conn, "SELECT id, status FROM tickets")}
    for t in (101, 102, 103):
        upd = [args for ag, name, args in A[t]["tool_calls"] if name == "update_ticket_status"]
        assert upd and upd[-1]["status"] == "resolved" and status[t] == "resolved"
        f[t].append(f"Status: the plan said <i>{EXPECTED[t]['status']}</i>; Boss set <code>resolved</code> "
                    "(the Problem 8 rule: resolved at end of run, with pending money shown as an \"approval pending\" badge).")

    # 101: cash Accounting saw was $1,000 (102 was paid first), not $3,400.
    cash101 = tool_result(A[101], "get_cash_balance", "accounting")
    assert '"checking_balance": 1000.0' in cash101
    f[101].append("Accounting saw <b>$1,000.00</b> in checking, not the $3,400 in the plan, because I ran and approved "
                  "ticket 102's rent first (see Cash tab).")
    assert not any(name == "request_purchase_order" for _, name, _ in A[101]["tool_calls"])
    f[101].append("No restock PO was requested for the tee. The plan said it waits until invoice 501 is paid, and "
                  "the ticket ended before that approval.")
    # 102: Accounting used list_obligations instead of get_invoice to see the $840.
    obl102 = tool_result(A[102], "list_obligations", "accounting")
    assert '"ref_id": 501' in obl102 and '"amount": 840.0' in obl102
    f[102].append("Accounting got invoice 501's $840 from <code>list_obligations</code> (all obligations at once) "
                  "instead of <code>get_invoice</code>, and still computed $3,240 owed and $160 left.")
    # 103: Bulldog was NOT blocked anymore (501 paid during 101); the blocker was cash.
    blocked103 = tool_result(A[103], "get_vendor_open_invoices", "inventory")
    assert '"blocked": false' in blocked103
    cash103 = tool_result(A[103], "get_cash_balance", "accounting")
    assert '"checking_balance": 160.0' in cash103
    f[103].append("The plan said Bulldog Print is blocked by invoice 501. By the time 103 ran, 501 was already paid "
                  "(ticket 101), so <code>get_vendor_open_invoices</code> returned <code>blocked: false</code>. The real "
                  "blocker was cash: 12 × $22.00 = $264.00 vs <b>$160.00</b> in checking.")
    prices = [args.get("proposed_price") for ag, name, args in A[103]["tool_calls"] if name == "get_pricing"]
    assert 50 in prices
    f[103].append("Accounting priced a <b>$50.00</b> bulk price (13.8% off $58.00 list, $28.00 margin per unit), "
                  "and Boss approved it. No PO was requested, so nothing was left for me to approve.")
    return f


# ---------------------------------------------------------------- HTML builders

def label(task: str, n: int = 70) -> str:
    task = re.sub(r"^Ticket \d+:\s*", "", task)
    return task if len(task) <= n else task[: n - 1].rstrip() + "…"


def actual_html(t: int, a: dict, diffs: list[str], ticket_facts: list[str], decision: dict, approvals: list[dict]) -> str:
    flow = [[f, to, label(task)] for f, to, task in a["delegations"]]
    flow.append(["boss", None, "Logged a note, set status → resolved"])
    flow_attr = e(json.dumps([[x[0], x[1], e(x[2])] for x in flow]), quote=True)
    chips = " ".join(f'<span class="agent-chip {ag}">{NAMES[ag]}</span>' for ag in a["agents"])
    dlist = "\n".join(f'        <li><b>{NAMES[f]} → {NAMES[to]}:</b> “{e(task)}”</li>' for f, to, task in a["delegations"])
    trows = "\n".join(
        f'          <tr><td class="num">{i}</td><td><span class="agent-chip {ag}">{NAMES[ag]}</span></td>'
        f'<td><code>{e(name)}</code></td><td class="mono-sm">{e(", ".join(f"{k}={v}" for k, v in args.items() if k not in ("note", "draft", "reason")))}</td></tr>'
        for i, (ag, name, args) in enumerate(a["tool_calls"], 1))
    appr = "".join(
        f"<li>Request #{r['id']}: {r['kind']} {money(r['amount'])}, requested by {e(r['requested_by'])}, "
        f"<b>{'approved' if r['status'] == 'executed' else r['status']}</b> by {e(r['decided_by'] or '—')}"
        f"{' (payment #' + str(r['payment_id']) + ')' if r['payment_id'] else ''}</li>" for r in approvals
    ) or "<li>None. No payment or PO requests were created for this ticket.</li>"
    refused = "".join(f"<li>{NAMES.get(ag, ag)} <code>{name}</code> refused</li>" for ag, name, _ in a["refused"]) or "<li>None</li>"
    diff_items = "\n".join(f"        <li>{d}</li>" for d in diffs + ticket_facts)
    return f'''<!-- ACTUAL:{t} START -->
    <div class="card actual-filled">
      <h2>Actual <small>run {a['run_id']} · {a['seconds']:.0f}s · {a['model_calls']} model calls · {len(a['tool_calls'])} MCP tool calls · {a['tokens']:,} tokens</small></h2>
      <div class="first"><b>Boss called first: {NAMES[a['first_call']]}.</b></div>
      <h3>Agents that worked</h3>
      <div class="chips">{chips}</div>
      <h3>Delegation flow</h3>
      <div class="flow" data-flow="{flow_attr}"></div>
      <h3>Every delegation, in order</h3>
      <ol class="plan">
{dlist}
      </ol>
      <h3>Every MCP tool called ({len(a['tool_calls'])})</h3>
      <table class="data">
        <thead><tr><th class="num">#</th><th>Agent</th><th>Tool</th><th>Arguments</th></tr></thead>
        <tbody>
{trows}
        </tbody>
      </table>
      <h3>Refused tool calls</h3><ul class="plan">{refused}</ul>
      <h3>Human approvals</h3><ul class="plan">{appr}</ul>
      <h3>Boss's final call</h3>
      <p>{e(decision['decision'])}</p>
      <div class="diff"><b>Expected vs Actual</b>
        <ul>
{diff_items}
        </ul>
      </div>
    </div>
    <!-- ACTUAL:{t} END -->'''


def cash_html(conn, order: list[int], A: dict) -> tuple[str, dict]:
    start = conn.execute("SELECT balance FROM original.cash_accounts WHERE name = 'checking'").fetchone()[0]
    reqs = rows(conn, "SELECT * FROM approval_requests ORDER BY id")
    pays = {p["id"]: p for p in rows(conn, "SELECT * FROM payments ORDER BY id")}
    tickets = {r["id"]: r for r in rows(conn, "SELECT id, subject FROM tickets")}
    pricing = {r["sku"]: r for r in rows(conn, "SELECT * FROM pricing")}
    body, running = [], start
    body.append(f'<tr><td>Start</td><td>Balance after reset (<code>original.cash_accounts</code>)</td>'
                f'<td class="num">—</td><td class="num">{money(start)}</td></tr>')
    for t in order:
        mine = [r for r in reqs if r["ticket_id"] == t]
        change, reasons = 0.0, []
        for r in mine:
            if r["status"] == "executed":
                p = pays[r["payment_id"]]
                change -= p["amount"]
                what = {"rent": f"Rent, lease {r['ref_id']}", "invoice": f"Invoice {r['ref_id']}",
                        "purchase_order": f"PO to vendor {r['vendor_id']} ({r['qty']} × {r['sku']} {r['size']})"}[r["kind"]]
                reasons.append(f"{what}: request #{r['id']} → payment #{p['id']}, {money(p['amount'])}, "
                               f"approved by <b>{e(p['approved_by'])}</b> on {p['paid_at']}")
            else:
                reasons.append(f"Request #{r['id']} ({r['kind']}, {money(r['amount'])}) {r['status']} by "
                               f"{e(r['decided_by'] or '—')}: {e(r['reason'])}. $0.00")
        if not mine:
            if t == 103:
                cost = pricing["CC-HOOD-NAVY"]["unit_cost"]
                reasons.append(f"No request created. Accounting priced the 12-unit restock at {money(12 * cost)} "
                               f"(12 × {money(cost)}) against {money(running)} available, so it didn't request a PO. $0.00")
            else:
                reasons.append("No request created. $0.00")
        running += change
        cls = "neg" if change < 0 else "zero"
        body.append(f'<tr><td>Ticket {t}<br><small>{e(tickets[t]["subject"])}</small></td><td>{"<br>".join(reasons)}</td>'
                    f'<td class="num {cls}">{money(change) if change else "$0.00"}</td><td class="num">{money(running)}</td></tr>')
    end = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()[0]
    body.append(f'<tr class="total"><td>End</td><td>Ending balance (<code>cash_accounts</code>)</td>'
                f'<td class="num">{money(running - start)}</td><td class="num">{money(end)}</td></tr>')
    assert abs(running - end) < 0.005, (running, end)

    refused_tool = [(t, ag, name) for t in order for ag, name, _ in A[t]["refused"]]
    rejected = [r for r in reqs if r["status"] == "rejected"]
    refused_lines = "".join(f"<li>Ticket {t}: {NAMES[ag]} <code>{name}</code> refused ($0.00)</li>" for t, ag, name in refused_tool)
    refused_lines += "".join(f"<li>Request #{r['id']} rejected by {e(r['decided_by'])}: {e(r['reason'])} ($0.00)</li>" for r in rejected)
    if not refused_lines:
        refused_lines = ("<li>None. <code>approval_requests</code> has no rejected rows, and no tool call in the "
                         "run was refused. The only money-related \"no\" was Accounting choosing not to request the "
                         "ticket 103 PO (row above).</li>")

    proof_sql = """ATTACH DATABASE 'data/campus_customs.db' AS original;  -- opened read-only

SELECT
  (SELECT balance FROM original.cash_accounts WHERE name = 'checking')          AS starting_balance,
  (SELECT COUNT(*) FROM payments)                                               AS payment_rows,
  (SELECT COALESCE(SUM(amount), 0) FROM payments)                               AS total_paid,
  (SELECT balance FROM original.cash_accounts WHERE name = 'checking')
    - (SELECT COALESCE(SUM(amount), 0) FROM payments)                           AS start_minus_payments,
  (SELECT balance FROM cash_accounts WHERE name = 'checking')                   AS cash_accounts_balance,
  (SELECT balance FROM original.cash_accounts WHERE name = 'checking')
    - (SELECT COALESCE(SUM(amount), 0) FROM payments)
    = (SELECT balance FROM cash_accounts WHERE name = 'checking')               AS reconciles;"""
    q = proof_sql.split(";", 1)[1].strip().rstrip(";")
    proof = dict(conn.execute(q).fetchone())
    assert proof["reconciles"] == 1
    proof_rows = "".join(f"<tr><td><code>{k}</code></td><td class='num'>{v}</td></tr>" for k, v in proof.items())
    html_out = f'''<!-- CASH START -->
    <div class="card">
      <h2>Cash, itemized <small>from <code>payments</code> + <code>approval_requests</code> in data/campus_customs_new.db</small></h2>
      <table class="data">
        <thead><tr><th>Step</th><th>Reason</th><th class="num">Cash change</th><th class="num">Running balance</th></tr></thead>
        <tbody>
          {chr(10).join(body)}
        </tbody>
      </table>
      <p class="flow-label" style="padding:4px 0 0">Tickets in the order they were run and approved (102 → 101 → 103).
        Agents only <i>requested</i>; every payment above was executed by a human approval.</p>
      <h3>Refused or rejected requests</h3>
      <ul class="plan">{refused_lines}</ul>
    </div>
    <div class="card">
      <h2>Proof: starting balance − payments = cash_accounts.balance</h2>
      <pre class="sql">{e(proof_sql)}</pre>
      <table class="data" style="max-width:520px"><tbody>{proof_rows}</tbody></table>
      <p class="{'ok' if proof['reconciles'] else 'neg'}">{money(proof['starting_balance'])} − {money(proof['total_paid'])} = {money(proof['start_minus_payments'])}, which matches cash_accounts ({money(proof['cash_accounts_balance'])}) ✓</p>
    </div>
    <!-- CASH END -->'''
    return html_out, {"sql": proof_sql, "result": proof}


def metrics_html(A: dict) -> str:
    rows_ = []
    for t in (101, 102, 103):
        a, exp = A[t], EXPECTED[t]
        rows_.append(
            f"<tr><td>{t}</td>"
            f"<td>{', '.join(NAMES[x] for x in AGENT_ORDER if x in exp['agents'])}</td>"
            f"<td>{', '.join(NAMES[x] for x in a['agents'])}</td>"
            f"<td class='num'>{len(exp['delegations'])} / {len(a['delegations'])}</td>"
            f"<td class='num'>{a['model_calls']}</td>"
            f"<td class='num'>{len(exp['tools'])} / {len(a['tool_calls'])}</td>"
            f"<td class='num'>{a['tokens']:,}</td>"
            f"<td class='num'>{a['seconds']:.0f}s</td></tr>")
    tot = {k: sum(A[t][k] for t in A) for k in ("model_calls", "tokens", "seconds")}
    rows_.append(f"<tr class='total'><td>All</td><td></td><td></td>"
                 f"<td class='num'>{sum(len(EXPECTED[t]['delegations']) for t in A)} / {sum(len(A[t]['delegations']) for t in A)}</td>"
                 f"<td class='num'>{tot['model_calls']}</td>"
                 f"<td class='num'>{sum(len(EXPECTED[t]['tools']) for t in A)} / {sum(len(A[t]['tool_calls']) for t in A)}</td>"
                 f"<td class='num'>{tot['tokens']:,}</td><td class='num'>{tot['seconds']:.0f}s</td></tr>")
    return f'''<!-- REFLECTION-METRICS START -->
    <div class="card">
      <h2>The run in numbers <small>audit trail events after the last reset marker</small></h2>
      <table class="data">
        <thead><tr><th>Ticket</th><th>Agents expected</th><th>Agents actual</th><th class="num">Delegations exp / act</th>
          <th class="num">Model calls</th><th class="num">MCP tools exp (distinct) / act (calls)</th><th class="num">Tokens</th><th class="num">Run time</th></tr></thead>
        <tbody>
          {chr(10).join(rows_)}
        </tbody>
      </table>
      <p class="flow-label" style="padding:4px 0 0">"MCP tools expected" counts the distinct tools in my plan; "actual" counts every MCP call (repeats included; <code>delegate</code> excluded). Run time is first to last audit event of the run.</p>
    </div>
    <!-- REFLECTION-METRICS END -->'''


def replace_block(s: str, name: str, new: str) -> str:
    pat = re.compile(rf"<!-- {re.escape(name)} START -->.*?<!-- {re.escape(name)} END -->", re.S)
    assert len(pat.findall(s)) == 1, name
    return pat.sub(lambda m: new, s)


# ---------------------------------------------------------------- main

def main() -> None:
    events, reset = load_events()
    conn = connect()
    A = {t: analyze(events, t) for t in (101, 102, 103)}
    order = sorted(A, key=lambda t: A[t]["started"])
    runs = {r["run_id"]: r for r in json.loads(RUNS.read_text(encoding="utf-8"))}
    decisions = {t: runs[A[t]["run_id"]]["decision"] for t in A}
    F = facts(conn, A)
    reqs = rows(conn, "SELECT * FROM approval_requests ORDER BY id")

    desk = DESK.read_text(encoding="utf-8")
    expected_before = re.findall(r'<div class="card">\s*<h2>Expected</h2>.*?</div>\s*</div>', desk, re.S)
    for t in (101, 102, 103):
        desk = replace_block(desk, f"ACTUAL:{t}", actual_html(
            t, A[t], compare(t, A[t]), F[t], decisions[t], [r for r in reqs if r["ticket_id"] == t]))
    cash_block, proof = cash_html(conn, order, A)
    desk = replace_block(desk, "CASH", cash_block)
    desk = replace_block(desk, "REFLECTION-METRICS", metrics_html(A))
    assert re.findall(r'<div class="card">\s*<h2>Expected</h2>.*?</div>\s*</div>', desk, re.S) == expected_before
    DESK.write_text(desk, encoding="utf-8")

    # ---- resolved_tickets.json
    tk = {r["id"]: r for r in rows(conn, "SELECT * FROM tickets")}
    drafts = {r["ticket_id"]: r for r in rows(conn, "SELECT * FROM customer_drafts")}
    stock = {(r["sku"], r["size"]): r["qty"] for r in rows(conn, "SELECT sku, size, qty FROM inventory")}
    lease = rows(conn, "SELECT * FROM leases WHERE id = 1")[0]
    inv = rows(conn, "SELECT * FROM invoices WHERE id = 501")[0]
    cost = rows(conn, "SELECT unit_cost FROM pricing WHERE sku = 'CC-HOOD-NAVY'")[0]["unit_cost"]
    balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()[0]
    r102 = next(r for r in reqs if r["ticket_id"] == 102)
    r101 = next(r for r in reqs if r["ticket_id"] == 101)
    outcomes = {
        101: (f"The size S tee is still out of stock ({stock[('CC-TEE-WHITE', 'S')]} on hand). Accounting requested the "
              f"overdue invoice {inv['id']} ({money(inv['amount'])}), I approved it (request #{r101['id']}), and the invoice "
              f"is now {inv['status']}, which unblocks Bulldog Print Co. No restock PO was requested, and the draft to "
              f"Tauhid promises no date."),
        102: (f"Rent of {money(lease['monthly_rent'])} for lease {lease['id']} was requested by Accounting and paid after my "
              f"approval (request #{r102['id']}); the lease's next due date moved to {lease['next_due']}."),
        103: (f"Boss approved a $50.00 bulk price (above the {money(cost)} unit cost) and Customer Service drafted an offer for "
              f"the {stock[('CC-HOOD-NAVY', 'M')]} hoodies in stock. The 12-unit restock ({money(12 * cost)}) was not "
              f"requested because only {money(balance)} was left."),
    }
    out = []
    for t in (101, 102, 103):
        a = A[t]
        contrib = []
        for ag in a["agents"]:
            tools = [name for g, name, _ in a["tool_calls"] if g == ag]
            text = decisions[t]["decision"] if ag == "boss" else a["reports"].get(ag)
            contrib.append({
                "agent": NAMES[ag],
                "contribution": text,
                "mcp_tools": sorted(set(tools), key=tools.index),
                "handed_off_to": [NAMES[to] for f, to, _ in a["delegations"] if f == ag],
            })
        out.append({
            "id": t,
            "subject": tk[t]["subject"],
            "requester": tk[t]["requester"],
            "final_status": tk[t]["status"],
            "outcome": outcomes[t],
            "run_id": a["run_id"],
            "agents": contrib,
            "customer_draft_id": drafts[t]["id"] if t in drafts else None,
            "human_approvals": [{
                "request_id": r["id"], "kind": r["kind"], "amount": r["amount"],
                "approved_by": r["decided_by"],
                "decision": "approved" if r["status"] == "executed" else r["status"],
                "payment_id": r["payment_id"],
            } for r in reqs if r["ticket_id"] == t],
        })
    RESOLVED.write_text(json.dumps({"source": "audit_trail.json events after reset marker "
                                    f"#{reset['id']} ({reset['timestamp']}) + data/campus_customs_new.db",
                                    "checking_balance": balance, "tickets": out}, indent=2) + "\n", encoding="utf-8")

    # ---- print what was used, for the record
    print(f"reset marker #{reset['id']} at {reset['timestamp']}; {len(events)} events after it")
    for t in order:
        a = A[t]
        print(f"ticket {t}: run {a['run_id']} | agents {a['agents']} | delegations {len(a['delegations'])} | "
              f"model calls {a['model_calls']} | MCP calls {len(a['tool_calls'])} | tokens {a['tokens']} | "
              f"{a['seconds']:.1f}s | refused {len(a['refused'])} | errors {len(a['errors'])}")
    print("proof query result:", proof["result"])
    print("wrote", DESK.name, "and", RESOLVED.name)


if __name__ == "__main__":
    main()
