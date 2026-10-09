"""Inventory: checks stock and shortfall, picks a restock vendor, checks if it's blocked."""

from backend.agents.shared import AgentSpec
from backend.models import AgentReport

SPEC = AgentSpec(
    name="inventory",
    display_name="Inventory",
    prompt_file="inventory.md",
    mcp_tools=frozenset({"check_stock", "find_vendors", "list_vendors", "get_vendor_open_invoices"}),
    output_type=AgentReport,
    usually_delegates_to=("accounting",),
)
