"""Facilities: leases and rent; works with Accounting to request rent payment."""

from backend.agents.shared import AgentSpec
from backend.models import AgentReport

SPEC = AgentSpec(
    name="facilities",
    display_name="Facilities",
    prompt_file="facilities.md",
    mcp_tools=frozenset({"get_lease", "get_cash_balance", "get_today"}),
    output_type=AgentReport,
    usually_delegates_to=("accounting",),
)
