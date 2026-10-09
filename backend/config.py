"""The one place for the model, the Portkey connection, paths, and run limits.

The model name below is the only one in the codebase. Every agent is built
with build_model(), so no agent ever falls back to a library default.
The Portkey key is read from the PORTKEY_API_KEY environment variable (or a
gitignored .env in the project root) and is never logged or printed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import UsageLimits
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# ---- Model (Portkey gateway, OpenAI Responses API)
MODEL_NAME = "gpt-6-Luna"
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")
PORTKEY_PROVIDER = "openai"

# ---- Paths
PROMPTS_DIR = BACKEND_DIR / "prompts"
MCP_SERVER_PATH = ROOT_DIR / "mcp_server" / "server.py"
MCP_PYTHON = sys.executable  # the interpreter running the backend (the project venv)
AUDIT_TRAIL_PATH = ROOT_DIR / "output" / "audit_trail.json"

# ---- Delegation and token limits (per ticket run, shared across all delegations)
MAX_DELEGATION_DEPTH = 3       # Boss = depth 0; a depth-3 agent cannot delegate further
MAX_TASK_CHARS = 800           # handoffs carry a short task description, never chat history
TICKET_USAGE_LIMITS = UsageLimits(
    request_limit=40,          # model calls across Boss + every delegated agent
    tool_calls_limit=60,       # MCP + delegate tool calls across the whole run
    total_tokens_limit=250_000,
)
AGENT_RETRIES = 2              # retries for malformed tool args / output per agent
AUDIT_RESULT_CHARS = 400       # tool results are truncated to this in the audit trail

# Tools only the human-approval step may call. Never given to any agent.
HUMAN_ONLY_TOOLS = frozenset({"execute_payment", "reject_request"})


def get_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Set it as an environment variable, or copy "
            ".env.example to .env in the project root and add your key."
        )
    return key


def build_model() -> OpenAIResponsesModel:
    client = AsyncOpenAI(
        api_key=get_api_key(),
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": PORTKEY_PROVIDER},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
