"""Append-only audit trail in output/audit_trail.json.

Every write reads the existing JSON array, appends, and writes the whole
array back atomically. The file is never wiped. Any occurrence of the
Portkey key is redacted before writing.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import AUDIT_RESULT_CHARS, AUDIT_TRAIL_PATH
from backend.models import AuditEntry, TokenUsage

_LOCK = threading.Lock()
_SECRET_ENV_VARS = ("PORTKEY_API_KEY",)


def _redact(text: str) -> str:
    for var in _SECRET_ENV_VARS:
        secret = os.getenv(var, "").strip()
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    return text


def short(value: Any, limit: int = AUDIT_RESULT_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def to_usage(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        total_tokens=(getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0),
        requests=getattr(usage, "requests", None),
    )


def _read(path: Path) -> list:
    if not path.exists() or path.stat().st_size == 0:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a JSON array; refusing to overwrite it.")
    return data


def _write(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(_redact(json.dumps(entries, indent=2, default=str)) + "\n", encoding="utf-8")
    for attempt in range(5):  # OneDrive can briefly lock the file
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.2 * (attempt + 1))
    os.replace(tmp, path)


def log(
    *,
    run_id: str,
    ticket_id: int,
    agent: str,
    step_type: str,
    depth: int,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    result: Any = None,
    step_usage: Any = None,
    run_usage: Any = None,
    path: Path = AUDIT_TRAIL_PATH,
) -> AuditEntry:
    entry = AuditEntry(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        run_id=run_id,
        ticket_id=ticket_id,
        agent=agent,
        step_type=step_type,
        tool_name=tool_name,
        tool_args=tool_args,
        result=None if result is None else _redact(short(result)),
        depth=depth,
        step_usage=to_usage(step_usage),
        run_usage=to_usage(run_usage),
    )
    with _LOCK:
        entries = _read(path)
        entries.append(entry.model_dump(mode="json"))
        _write(path, entries)
    return entry
