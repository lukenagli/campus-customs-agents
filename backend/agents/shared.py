"""Shared wiring for the agent team.

- Loads each agent's system prompt from backend/prompts/.
- Connects to the Campus Customs MCP server (stdio) and gives each agent a
  filtered view with only the MCP tools it needs. Human-only tools are never
  exposed to any agent.
- Gives every agent a `delegate` tool that can hand a short task to any other
  agent, with a depth cap, no cycles, and usage shared across the whole run.
- Walks every agent run step by step and appends each step to the audit trail.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart

from backend import audit
from backend.config import (
    AGENT_RETRIES,
    HUMAN_ONLY_TOOLS,
    MAX_DELEGATION_DEPTH,
    MAX_TASK_CHARS,
    MCP_PYTHON,
    MCP_SERVER_PATH,
    PROMPTS_DIR,
    ROOT_DIR,
    TICKET_USAGE_LIMITS,
    build_model,
)
from backend.models import AgentName, AgentReport, DelegationResult, TicketDecision

if TYPE_CHECKING:
    from pydantic_ai.models import Model

FINAL_ANSWER_CHARS = 1500


@dataclass(frozen=True)
class AgentSpec:
    """Everything that defines one agent: name, prompt file, tools, output type."""
    name: AgentName
    display_name: str
    prompt_file: str
    mcp_tools: frozenset[str]
    output_type: type[BaseModel]
    usually_delegates_to: tuple[AgentName, ...] = ()

    def __post_init__(self) -> None:
        leaked = self.mcp_tools & HUMAN_ONLY_TOOLS
        if leaked:
            raise ValueError(f"{self.name} must never get human-only tools: {sorted(leaked)}")


@dataclass
class RunDeps:
    """Per-step context passed to every agent run. Never logged."""
    team: Team
    run_id: str
    ticket_id: int
    agent: AgentName
    depth: int = 0
    chain: tuple[AgentName, ...] = field(default_factory=tuple)


def load_prompt(prompt_file: str) -> str:
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")


def build_mcp_toolset() -> MCPToolset:
    """One stdio connection to mcp_server/server.py, shared by every agent in a run."""
    # keep_alive=False: the server process exits when the run closes its connection.
    transport = StdioTransport(command=MCP_PYTHON, args=[str(MCP_SERVER_PATH)], cwd=str(ROOT_DIR), keep_alive=False)
    return MCPToolset(Client(transport), id="campus-customs")


# ---------------------------------------------------------------- delegation tool

async def delegate(ctx: RunContext[RunDeps], to_agent: AgentName, task: str) -> DelegationResult:
    """Hand a short, self-contained task to another agent and get its report back.

    to_agent: one of boss, inventory, accounting, facilities, customer_service
    (not yourself). task: 1-3 sentences with the ticket id and the specific
    facts and question (SKU/size/qty, invoice_id, lease_id, amounts). Do not
    paste conversation history. Delegation depth is capped and an agent that
    is already working on this chain cannot be asked again.
    """
    d = ctx.deps
    base = {"from_agent": d.agent, "to_agent": to_agent, "depth": d.depth + 1}

    def refuse(error: str) -> DelegationResult:
        audit.log(run_id=d.run_id, ticket_id=d.ticket_id, agent=d.agent, step_type="error",
                  depth=d.depth, tool_name="delegate", tool_args={"to_agent": to_agent}, result=error)
        return DelegationResult(ok=False, error=error, **base)

    if to_agent == d.agent:
        return refuse("You cannot delegate to yourself.")
    if d.depth >= MAX_DELEGATION_DEPTH:
        return refuse(f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached. Finish with what you have.")
    if to_agent in d.chain:
        return refuse(f"{to_agent} is already working on this chain ({' -> '.join(d.chain)}). "
                      "Answer with what you have instead of looping back.")
    task = " ".join((task or "").split())
    if not task:
        return refuse("Task cannot be empty.")
    if len(task) > MAX_TASK_CHARS:
        task = task[: MAX_TASK_CHARS - 3] + "..."

    audit.log(run_id=d.run_id, ticket_id=d.ticket_id, agent=d.agent, step_type="delegation_sent",
              depth=d.depth + 1, tool_name="delegate", tool_args={"to_agent": to_agent, "task": task},
              run_usage=ctx.usage)

    child = replace(d, agent=to_agent, depth=d.depth + 1, chain=d.chain + (to_agent,))
    prompt = f"Task from {d.agent} (ticket {d.ticket_id}):\n{task}"
    try:
        report = await d.team.run_agent(to_agent, prompt, child, ctx.usage, as_delegate=True)
    except UsageLimitExceeded:
        raise  # the cap is per ticket run: stop everything
    except Exception as exc:  # report the failure to the caller instead of crashing the run
        return refuse(f"{to_agent} failed: {type(exc).__name__}: {exc}")

    audit.log(run_id=d.run_id, ticket_id=d.ticket_id, agent=to_agent, step_type="delegation_returned",
              depth=d.depth + 1, tool_name="delegate", tool_args={"returned_to": d.agent},
              result=report.summary, run_usage=ctx.usage)
    return DelegationResult(ok=True, report=report, **base)


# ---------------------------------------------------------------- team

class Team:
    """The five agents, one shared MCP connection, and an audited run loop."""

    def __init__(self, specs: dict[str, AgentSpec], model: Model | None = None,
                 mcp_toolset: MCPToolset | None = None) -> None:
        self.specs = specs
        self.model = model or build_model()
        self.mcp = mcp_toolset or build_mcp_toolset()
        self.agents: dict[str, Agent] = {name: self._build_agent(spec) for name, spec in specs.items()}

    def _build_agent(self, spec: AgentSpec) -> Agent:
        allowed = spec.mcp_tools
        scoped = self.mcp.filtered(lambda ctx, tool_def, allowed=allowed: tool_def.name in allowed)
        agent = Agent(
            self.model,
            name=spec.name,
            instructions=load_prompt(spec.prompt_file),
            deps_type=RunDeps,
            output_type=spec.output_type,
            toolsets=[scoped],
            tools=[delegate],
            retries=AGENT_RETRIES,
        )

        @agent.instructions
        def run_context(ctx: RunContext[RunDeps]) -> str:
            d = ctx.deps
            others = ", ".join(n for n in self.specs if n != d.agent and n not in d.chain) or "none"
            return (f"Ticket: {d.ticket_id}. Delegation depth: {d.depth} of {MAX_DELEGATION_DEPTH} "
                    f"(chain: {' -> '.join(d.chain)}). Agents you may still delegate to: "
                    f"{others if d.depth < MAX_DELEGATION_DEPTH else 'none (depth limit reached)'}.")

        return agent

    async def run_agent(self, name: str, prompt: str, deps: RunDeps, usage: RunUsage,
                        as_delegate: bool = False) -> Any:
        """Run one agent to completion, logging every loop step to the audit trail."""
        agent = self.agents[name]
        # Boss returns a TicketDecision when running a ticket, but a plain report when another
        # agent delegates a question to it.
        output_type = AgentReport if (as_delegate and self.specs[name].output_type is not AgentReport) else None
        log = lambda **kw: audit.log(run_id=deps.run_id, ticket_id=deps.ticket_id, agent=name,  # noqa: E731
                                     depth=deps.depth, **kw)

        async with agent.iter(prompt, deps=deps, usage=usage, usage_limits=TICKET_USAGE_LIMITS,
                              output_type=output_type) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    response = node.model_response
                    calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
                    text = " ".join(p.content for p in response.parts if isinstance(p, TextPart)).strip()
                    said = text or ("calls: " + ", ".join(c.tool_name for c in calls) if calls else "")
                    log(step_type="model_call", result=said, step_usage=response.usage, run_usage=usage)
                    for call in calls:
                        if call.tool_name.startswith("final_result"):
                            continue  # logged as final_answer below
                        log(step_type="tool_call", tool_name=call.tool_name, tool_args=call.args_as_dict())
                elif Agent.is_model_request_node(node):
                    for part in node.request.parts:
                        if isinstance(part, ToolReturnPart) and not part.tool_name.startswith("final_result"):
                            content = part.content
                            if isinstance(content, BaseModel):
                                content = content.model_dump(mode="json", exclude_none=True)
                            log(step_type="tool_result", tool_name=part.tool_name, result=content)
                        elif isinstance(part, RetryPromptPart) and part.tool_name:
                            log(step_type="tool_result", tool_name=part.tool_name,
                                result=f"retry: {part.model_response()}")
                elif Agent.is_end_node(node):
                    output = node.data.output
                    log(step_type="final_answer",
                        result=audit.short(output.model_dump(mode="json", exclude_none=True), FINAL_ANSWER_CHARS),
                        run_usage=usage)
            return run.result.output

    async def run_ticket(self, ticket_id: int, run_id: str | None = None) -> dict:
        """Boss works one ticket end to end, under one shared usage cap."""
        run_id = run_id or uuid.uuid4().hex[:12]
        usage = RunUsage()
        deps = RunDeps(team=self, run_id=run_id, ticket_id=ticket_id, agent="boss", chain=("boss",))
        audit.log(run_id=run_id, ticket_id=ticket_id, agent="boss", step_type="run_started", depth=0,
                  result=f"Ticket {ticket_id} run started. Limits: depth {MAX_DELEGATION_DEPTH}, "
                         f"{TICKET_USAGE_LIMITS.request_limit} requests, "
                         f"{TICKET_USAGE_LIMITS.total_tokens_limit} total tokens.")
        prompt = (f"Handle ticket {ticket_id}. Start with get_ticket({ticket_id}), route it to the right "
                  "specialists, make the final call, log a note, and set the status.")
        try:
            async with self.mcp:  # one MCP connection for Boss and every delegated agent
                decision: TicketDecision = await self.run_agent("boss", prompt, deps, usage)
        except UsageLimitExceeded as exc:
            audit.log(run_id=run_id, ticket_id=ticket_id, agent="boss", step_type="error", depth=0,
                      result=f"Usage limit reached, run stopped: {exc}", run_usage=usage)
            return {"ok": False, "run_id": run_id, "ticket_id": ticket_id, "error": str(exc),
                    "usage": audit.to_usage(usage).model_dump()}
        except Exception as exc:
            audit.log(run_id=run_id, ticket_id=ticket_id, agent="boss", step_type="error", depth=0,
                      result=f"{type(exc).__name__}: {exc}", run_usage=usage)
            raise
        return {"ok": True, "run_id": run_id, "ticket_id": ticket_id,
                "decision": json.loads(decision.model_dump_json()),
                "usage": audit.to_usage(usage).model_dump()}
