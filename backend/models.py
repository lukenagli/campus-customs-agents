"""Pydantic data types shared by the agent team and the audit trail."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "waiting_on_restock", "resolved"]
StepType = Literal[
    "run_started", "model_call", "tool_call", "tool_result",
    "delegation_sent", "delegation_returned", "final_answer", "error",
    "human_decision", "status_change", "database_reset",
]


# ---- Requests the agents create (always pending a human)

class PaymentRequest(BaseModel):
    """A pending payment an agent asked a human to approve."""
    request_id: int | None = Field(None, description="approval_requests.id returned by request_payment")
    kind: Literal["invoice", "rent"]
    ref_id: int = Field(description="invoices.id or leases.id")
    amount: float
    reason: str


class PurchaseOrderRequest(BaseModel):
    """A pending restock purchase order an agent asked a human to approve."""
    request_id: int | None = None
    vendor_id: int
    sku: str
    size: str
    qty: int
    estimated_cost: float | None = None
    reason: str


class CustomerDraft(BaseModel):
    """A message saved on the board for a human to review. Never sent."""
    ticket_id: int
    draft_id: int | None = Field(None, description="customer_drafts.id returned by save_customer_draft")
    recipient: str
    message: str


# ---- Delegation

class DelegationRequest(BaseModel):
    """A short handoff from one agent to another (no chat history)."""
    from_agent: AgentName
    to_agent: AgentName
    ticket_id: int
    task: str
    depth: int


class AgentReport(BaseModel):
    """What a specialist agent hands back after a delegated task."""
    agent: AgentName
    summary: str = Field(description="2-4 sentences answering the task, with the actual numbers")
    facts: list[str] = Field(default_factory=list, description="Key facts from tools, each with its number/date")
    actions_taken: list[str] = Field(default_factory=list, description="Writes made via tools (requests, drafts)")
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrderRequest] = Field(default_factory=list)
    customer_draft: CustomerDraft | None = None
    recommendation: str = ""
    data_gaps: list[str] = Field(default_factory=list, description="Anything the tools could not answer")


class DelegationResult(BaseModel):
    """What the delegate tool returns to the agent that asked."""
    ok: bool
    from_agent: AgentName
    to_agent: AgentName
    depth: int
    report: AgentReport | None = None
    error: str | None = None


# ---- Boss's final output for a ticket

class TicketDecision(BaseModel):
    """Boss's final call on a ticket."""
    ticket_id: int
    ticket_type: str
    routed_to: list[AgentName] = Field(description="Agents Boss delegated to, in order")
    decision: str = Field(description="The final call in 2-4 sentences, with the numbers behind it")
    discount_decision: str | None = Field(None, description="Approved/declined discount and price, if relevant")
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrderRequest] = Field(default_factory=list)
    customer_draft_saved: bool = False
    final_status: TicketStatus
    note_logged: bool = False
    open_questions: list[str] = Field(default_factory=list)


# ---- Audit trail

class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int | None = None


class AuditEntry(BaseModel):
    """One step of the agent loop. Never contains credentials or hidden reasoning."""
    timestamp: str
    run_id: str
    ticket_id: int
    agent: str
    step_type: StepType
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    result: str | None = None
    depth: int = 0
    step_usage: TokenUsage | None = None
    run_usage: TokenUsage | None = None
