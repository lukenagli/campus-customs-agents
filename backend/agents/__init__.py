"""The Campus Customs agent team."""

from backend.agents import accounting, boss, customer_service, facilities, inventory
from backend.agents.shared import AgentSpec, Team

SPECS: dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (boss.SPEC, inventory.SPEC, accounting.SPEC, facilities.SPEC, customer_service.SPEC)
}


def build_team() -> Team:
    return Team(SPECS)


__all__ = ["SPECS", "AgentSpec", "Team", "build_team"]
