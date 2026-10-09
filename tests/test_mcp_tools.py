"""Exercise the MCP tools through FastMCP's in-memory Client.

Usage (from any folder):
    python tests/test_mcp_tools.py
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp_server"))

from fastmcp import Client  # noqa: E402

from server import mcp  # noqa: E402

CALLS = [
    ("Ticket 101", "get_invoice", {"invoice_id": 501}),
    ("Ticket 102", "get_lease", {"lease_id": 1}),
    ("Ticket 103", "check_stock", {"sku": "CC-HOOD-NAVY", "size": "M", "qty_needed": 20}),
    ("Bad input: missing invoice", "get_invoice", {"invoice_id": 999}),
    ("Bad input: missing lease", "get_lease", {"lease_id": 42}),
    ("Bad input: wrong size", "check_stock", {"sku": "CC-HOOD-NAVY", "size": "XXL"}),
    ("Bad input: unknown SKU", "check_stock", {"sku": "CC-SOCKS", "size": "M"}),
]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


async def main() -> None:
    before = {p.name: md5(p) for p in (ROOT / "data").glob("*.db")}

    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("Tools:", ", ".join(t.name for t in tools))
        for label, name, args in CALLS:
            result = await client.call_tool(name, args)
            print(f"\n--- {label}: {name}({args})")
            print(json.dumps(result.structured_content, indent=2))

    after = {p.name: md5(p) for p in (ROOT / "data").glob("*.db")}
    print("\nDatabases unchanged by tool calls:", before == after)


if __name__ == "__main__":
    asyncio.run(main())
