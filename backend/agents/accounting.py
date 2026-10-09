"""Accounting: cash vs everything owed, invoices, margins, and pending payment/PO requests."""

from backend.agents.shared import AgentSpec
from backend.models import AgentReport

SPEC = AgentSpec(
    name="accounting",
    display_name="Accounting",
    prompt_file="accounting.md",
    mcp_tools=frozenset({
        "get_cash_balance", "list_obligations", "get_invoice", "get_vendor_open_invoices",
        "get_pricing", "list_approval_requests", "request_payment", "request_purchase_order",
    }),
    output_type=AgentReport,
    usually_delegates_to=("facilities", "inventory"),
)
