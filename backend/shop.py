"""The backend's own connection to the Campus Customs MCP server.

The API routes never touch SQLite directly. Reads, status updates, and the
human-only execute_payment / reject_request tools all go through this
client. Agents never see this client; they get their own filtered toolsets.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from backend.config import MCP_PYTHON, MCP_SERVER_PATH, ROOT_DIR


class ShopError(RuntimeError):
    pass


class Shop:
    def __init__(self) -> None:
        self._transport = StdioTransport(command=MCP_PYTHON, args=[str(MCP_SERVER_PATH)], cwd=str(ROOT_DIR),
                                         keep_alive=False)
        self._client = Client(self._transport)
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self._client.__aenter__()

    async def stop(self) -> None:
        # Bounded so a slow MCP child can never block a --reload or Ctrl+C shutdown.
        try:
            await asyncio.wait_for(self._client.__aexit__(None, None, None), timeout=5)
        except Exception:
            pass
        try:
            await asyncio.wait_for(self._transport.close(), timeout=5)
        except Exception:
            pass

    async def call(self, tool: str, **args: Any) -> dict:
        async with self._lock:  # one request at a time over the stdio pipe
            result = await self._client.call_tool(tool, args, raise_on_error=False)
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise ShopError(f"{tool} failed: {text}")
        if result.structured_content is not None:
            return result.structured_content
        return json.loads(result.content[0].text)
