"""Customer Service: honest draft replies to customers, saved on the board, never sent."""

from backend.agents.shared import AgentSpec
from backend.models import AgentReport

SPEC = AgentSpec(
    name="customer_service",
    display_name="Customer Service",
    prompt_file="customer_service.md",
    mcp_tools=frozenset({"get_ticket", "save_customer_draft"}),
    output_type=AgentReport,
    usually_delegates_to=(),
)
