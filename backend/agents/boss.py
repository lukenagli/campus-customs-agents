"""Boss: reads each ticket, routes it, makes the final call, and updates the board."""

from backend.agents.shared import AgentSpec
from backend.models import TicketDecision

SPEC = AgentSpec(
    name="boss",
    display_name="Boss",
    prompt_file="boss.md",
    mcp_tools=frozenset({"get_ticket", "list_open_tickets", "get_today", "add_ticket_note", "update_ticket_status"}),
    output_type=TicketDecision,
    usually_delegates_to=("inventory", "accounting", "facilities", "customer_service"),
)
