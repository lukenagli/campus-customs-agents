"""Campus Customs backend: FastAPI routes for the React dashboard.

Start from inside backend/:
    uvicorn main:app --reload --port 8000

- Every path is built from this file's location, so it works from backend/.
- All shop data goes through the MCP server (backend/shop.py). There is no SQL here.
- During a run, files are written only to output/ and data/, never to backend/,
  so --reload doesn't restart the server mid-run.
- How a ticket becomes "resolved": when a run finishes, Boss sets the ticket
  to resolved after its final call. If Boss didn't, the backend sets it. Any
  payment or purchase-order requests still pending stay on /approvals, and the
  board shows the ticket as resolved with an "approval pending" badge. Approving
  or rejecting them adds a note to the ticket but doesn't change its status.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, so `backend.*` imports work

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import audit  # noqa: E402
from backend.agents import SPECS, build_team  # noqa: E402
from backend.config import AUDIT_TRAIL_PATH, ROOT_DIR  # noqa: E402
from backend.shop import Shop, ShopError  # noqa: E402
from reset_db import reset_db  # noqa: E402

RUNS_PATH = ROOT_DIR / "output" / "runs.json"
CORS_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:3000", "http://127.0.0.1:3000",
]

shop = Shop()
runs: dict[str, dict] = {}        # run_id -> run record (persisted to output/runs.json)
active: dict[int, str] = {}       # ticket_id -> run_id while a run is in progress
tasks: set[asyncio.Task] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_runs() -> None:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_PATH.write_text(json.dumps(list(runs.values()), indent=2, default=str), encoding="utf-8")


def _load_runs() -> None:
    if RUNS_PATH.exists():
        for r in json.loads(RUNS_PATH.read_text(encoding="utf-8")):
            if r.get("status") == "running":  # the server stopped mid-run
                r["status"], r["error"] = "interrupted", "Server restarted during the run."
            runs[r["run_id"]] = r


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_runs()
    await shop.start()
    try:
        yield
    finally:
        await shop.stop()


app = FastAPI(title="Campus Customs Multi-Agent Operations", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


async def shop_call(tool: str, **args: Any) -> dict:
    try:
        return await shop.call(tool, **args)
    except ShopError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def pending_requests() -> list[dict]:
    return (await shop_call("list_approval_requests", status="pending"))["requests"]


# ---------------------------------------------------------------- tickets

@app.get("/tickets")
async def list_tickets() -> dict:
    """All tickets with status, pending approvals, and whether a run is active."""
    tickets = (await shop_call("list_tickets"))["tickets"]
    pending = await pending_requests()
    last_run = {}
    for r in runs.values():
        last_run[r["ticket_id"]] = r
    for t in tickets:
        mine = [p for p in pending if p["ticket_id"] == t["id"]]
        t["pending_approvals"] = len(mine)
        t["pending_amount"] = round(sum(p["amount"] for p in mine), 2)
        t["running"] = t["id"] in active
        t["run_id"] = active.get(t["id"]) or (last_run.get(t["id"]) or {}).get("run_id")
        t["last_run_status"] = (last_run.get(t["id"]) or {}).get("status")
    return {"tickets": tickets}


async def _run_ticket(ticket_id: int, run_id: str) -> None:
    record = runs[run_id]
    try:
        result = await build_team().run_ticket(ticket_id, run_id=run_id)
        record.update(status="completed" if result["ok"] else "failed",
                      decision=result.get("decision"), usage=result.get("usage"), error=result.get("error"))
        if result["ok"]:
            ticket = (await shop.call("get_ticket", ticket_id=ticket_id))["ticket"]
            if ticket["status"] != "resolved":  # Boss should do this; make sure board and run agree
                await shop.call("update_ticket_status", ticket_id=ticket_id, status="resolved")
                audit.log(run_id=run_id, ticket_id=ticket_id, agent="system", step_type="status_change", depth=0,
                          result=f"Run finished; ticket {ticket_id} set from {ticket['status']} to resolved.")
    except Exception as exc:  # keep the server alive; the failure shows in /runs and the audit trail
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        record["finished_at"] = _now()
        active.pop(ticket_id, None)
        _save_runs()


@app.post("/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    """Start the agent team on one ticket in the background. Returns a run_id right away."""
    found = await shop_call("get_ticket", ticket_id=ticket_id)
    if not found.get("found"):
        raise HTTPException(404, f"Ticket {ticket_id} not found.")
    if ticket_id in active:
        raise HTTPException(409, f"Ticket {ticket_id} is already running (run {active[ticket_id]}).")
    if found["ticket"]["status"] == "resolved":
        raise HTTPException(409, f"Ticket {ticket_id} is already resolved.")

    run_id = uuid.uuid4().hex[:12]
    active[ticket_id] = run_id
    runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "started_at": _now(),
                    "finished_at": None, "decision": None, "usage": None, "error": None}
    _save_runs()
    await shop_call("update_ticket_status", ticket_id=ticket_id, status="in_progress")
    task = asyncio.create_task(_run_ticket(ticket_id, run_id))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"run_id": run_id, "ticket_id": ticket_id, "status": "running"}


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    if run_id not in runs:
        raise HTTPException(404, f"Run {run_id} not found.")
    return runs[run_id]


# ---------------------------------------------------------------- events + summary

def _read_audit() -> list[dict]:
    if not AUDIT_TRAIL_PATH.exists():
        return []
    entries = json.loads(AUDIT_TRAIL_PATH.read_text(encoding="utf-8"))
    for i, e in enumerate(entries):
        e["id"] = i
    return entries


@app.get("/events")
async def events(since: str | None = None, ticket_id: int | None = None, run_id: str | None = None,
                 limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Recent audit-trail events, newest first.

    since: an event id (only events with a higher id) or an ISO timestamp.
    """
    entries = _read_audit()
    if since:
        if since.isdigit():
            entries = [e for e in entries if e["id"] > int(since)]
        else:
            entries = [e for e in entries if e["timestamp"] > since]
    if ticket_id is not None:
        entries = [e for e in entries if e["ticket_id"] == ticket_id]
    if run_id:
        entries = [e for e in entries if e["run_id"] == run_id]
    entries = list(reversed(entries))[:limit]
    return {"count": len(entries), "latest_id": entries[0]["id"] if entries else None,
            "active_runs": dict(active), "events": entries}


@app.get("/tickets/{ticket_id}/summary")
async def ticket_summary(ticket_id: int, run_id: str | None = None) -> dict:
    """Per-agent summary of a ticket's latest run (or a given run), built from the audit trail."""
    entries = [e for e in _read_audit() if e["ticket_id"] == ticket_id]
    if not run_id:
        starts = [e["run_id"] for e in entries if e["step_type"] == "run_started"]
        if not starts:
            raise HTTPException(404, f"No runs found for ticket {ticket_id}.")
        run_id = starts[-1]
    entries = [e for e in entries if e["run_id"] == run_id]

    agents: dict[str, dict] = {}

    def slot(name: str) -> dict:
        return agents.setdefault(name, {"agent": name, "model_calls": 0, "tokens": 0, "tools_used": {},
                                        "handed_off_to": [], "received_from": [], "summary": None})

    for e in entries:
        a = e["agent"]
        if a not in SPECS:
            continue
        if e["step_type"] == "model_call":
            s = slot(a)
            s["model_calls"] += 1
            s["tokens"] += (e.get("step_usage") or {}).get("total_tokens", 0)
        elif e["step_type"] == "tool_call" and e["tool_name"] != "delegate":
            tools = slot(a)["tools_used"]
            tools[e["tool_name"]] = tools.get(e["tool_name"], 0) + 1
        elif e["step_type"] == "delegation_sent":
            to = (e.get("tool_args") or {}).get("to_agent")
            slot(a)["handed_off_to"].append({"to": to, "task": (e.get("tool_args") or {}).get("task")})
            if to:
                slot(to)["received_from"].append(a)
        elif e["step_type"] == "delegation_returned":
            slot(a)["summary"] = e.get("result")  # the specialist's own summary, untruncated by JSON
        elif e["step_type"] == "final_answer" and not slot(a)["summary"]:
            text = e.get("result") or ""
            try:
                data = json.loads(text)
                slot(a)["summary"] = data.get("summary") or data.get("decision")
            except json.JSONDecodeError:
                slot(a)["summary"] = None
    order = [n for n in SPECS if n in agents]
    run = runs.get(run_id, {})
    if run.get("decision") and "boss" in agents:
        agents["boss"]["summary"] = run["decision"].get("decision")
    return {"ticket_id": ticket_id, "run_id": run_id, "status": run.get("status"),
            "decision": run.get("decision"), "usage": run.get("usage"),
            "agents": [agents[n] for n in order]}


# ---------------------------------------------------------------- approvals + cash

class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1)


class RejectBody(BaseModel):
    approved_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


@app.get("/approvals")
async def approvals() -> dict:
    """Pending payment and purchase-order requests, with their ticket, amount, reason, and requesting agent."""
    pending = await pending_requests()
    cash = await shop_call("get_cash_balance")
    return {"checking_balance": cash["checking_balance"], "pending_total": cash["pending_total"],
            "available_after_pending": cash["available_after_pending"], "approvals": pending}


async def _find_request(request_id: int) -> dict:
    for r in (await shop_call("list_approval_requests"))["requests"]:
        if r["id"] == request_id:
            return r
    raise HTTPException(404, f"Approval request {request_id} not found.")


@app.post("/approvals/{request_id}/approve")
async def approve(request_id: int, body: ApproveBody) -> dict:
    """The ONLY route that moves cash, via the MCP server's human-only execute_payment tool."""
    req = await _find_request(request_id)
    result = await shop_call("execute_payment", request_id=request_id, approved_by=body.approved_by)
    audit.log(run_id="human", ticket_id=req["ticket_id"], agent="human", step_type="human_decision", depth=0,
              tool_name="execute_payment", tool_args={"request_id": request_id, "approved_by": body.approved_by},
              result=result)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Payment refused."))
    return result


@app.post("/approvals/{request_id}/reject")
async def reject(request_id: int, body: RejectBody) -> dict:
    """Mark a pending request rejected. No cash moves."""
    req = await _find_request(request_id)
    result = await shop_call("reject_request", request_id=request_id, rejected_by=body.approved_by,
                             reason=body.reason)
    audit.log(run_id="human", ticket_id=req["ticket_id"], agent="human", step_type="human_decision", depth=0,
              tool_name="reject_request",
              tool_args={"request_id": request_id, "rejected_by": body.approved_by, "reason": body.reason},
              result=result)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Rejection refused."))
    return result


@app.get("/cash")
async def cash() -> dict:
    """Checking balance from cash_accounts plus every payment made so far."""
    payments = await shop_call("list_payments")
    balance = await shop_call("get_cash_balance")
    return {"today": balance["today"], "checking_balance": payments["checking_balance"],
            "payments": payments["payments"],
            "total_paid": payments["total_paid"], "pending_total": balance["pending_total"],
            "available_after_pending": balance["available_after_pending"]}


# ---------------------------------------------------------------- reset

@app.post("/reset")
async def reset() -> dict:
    """Copy the original DB over the working copy. The audit trail is kept and gets a marker event."""
    if active:
        raise HTTPException(409, f"Can't reset while tickets are running: {sorted(active)}.")
    path = reset_db()
    audit.log(run_id="reset", ticket_id=0, agent="human", step_type="database_reset", depth=0,
              result=f"Database reset: {path.name} recopied from campus_customs.db.")
    balance = await shop_call("get_cash_balance")
    return {"ok": True, "database": path.name, "checking_balance": balance["checking_balance"]}


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "active_runs": dict(active)}
