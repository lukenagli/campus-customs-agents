"""Run the agent team on one ticket from the command line.

Usage (from the project root or backend/):
    python backend/run_ticket.py 102
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents import build_team  # noqa: E402


async def main(ticket_id: int) -> None:
    result = await build_team().run_ticket(ticket_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        sys.exit("Usage: python backend/run_ticket.py <ticket_id>")
    asyncio.run(main(int(sys.argv[1])))
