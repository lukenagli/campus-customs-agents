"""Check each MCP tool output in output/mcp_smoke.json against the working DB.

Every expected value is recomputed with direct SQL (dates via julianday),
independent of the MCP server code. Writes "verified_against_db" into each
entry and prints any field that doesn't match.

Usage (from any folder):
    python tests/verify_mcp_smoke.py
"""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "campus_customs_new.db"
SMOKE_PATH = ROOT / "output" / "mcp_smoke.json"

TODAY = "(SELECT date_today FROM desk LIMIT 1)"

QUERIES = {
    "get_invoice": f"""
        SELECT 1 AS found, i.id AS invoice_id, i.amount, i.due_date, i.status, i.description,
               v.id AS vendor_id, v.name AS vendor_name, v.specialty AS vendor_specialty,
               v.lead_days AS vendor_lead_days, {TODAY} AS today,
               (i.status = 'open' AND julianday({TODAY}) > julianday(i.due_date)) AS is_overdue,
               CASE WHEN i.status = 'open' AND julianday({TODAY}) > julianday(i.due_date)
                    THEN CAST(julianday({TODAY}) - julianday(i.due_date) AS INTEGER) ELSE 0 END
                   AS days_overdue,
               (i.status = 'open') AS vendor_blocked
        FROM invoices i LEFT JOIN vendors v ON v.id = i.vendor_id
        WHERE i.id = :invoice_id
    """,
    "get_lease": f"""
        SELECT 1 AS found, id AS lease_id, space_name, landlord, monthly_rent, next_due, notes,
               {TODAY} AS today,
               CAST(julianday(next_due) - julianday({TODAY}) AS INTEGER) AS days_until_due,
               (julianday(next_due) < julianday({TODAY})) AS is_overdue,
               MAX(0, CAST(julianday({TODAY}) - julianday(next_due) AS INTEGER)) AS days_overdue
        FROM leases WHERE id = :lease_id
    """,
    "check_stock": """
        SELECT 1 AS found, sku, name, size, qty AS qty_on_hand, location,
               :qty_needed AS qty_needed,
               MAX(:qty_needed - qty, 0) AS shortfall,
               (qty >= :qty_needed) AS can_fulfill
        FROM inventory WHERE sku = :sku AND size = :size
    """,
}

BOOL_FIELDS = {"found", "is_overdue", "vendor_blocked", "can_fulfill"}


def main() -> None:
    entries = json.loads(SMOKE_PATH.read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    all_ok = True
    for entry in entries:
        tool = entry["tool"].rsplit("__", 1)[-1]
        row = conn.execute(QUERIES[tool], entry["arguments"]).fetchone()
        expected = {k: (bool(row[k]) if k in BOOL_FIELDS else row[k]) for k in row.keys()}

        output = entry["output"]
        mismatches = [
            f"{k}: tool={output.get(k)!r} db={v!r}"
            for k, v in expected.items()
            if output.get(k) != v or isinstance(output.get(k), bool) != isinstance(v, bool)
        ]
        extra = sorted(set(output) - set(expected))
        if extra:
            mismatches.append(f"fields not checked by SQL: {extra}")

        entry["verified_against_db"] = not mismatches
        all_ok &= not mismatches
        print(f"{entry['tool']}({entry['arguments']}): "
              f"{'OK' if not mismatches else 'MISMATCH'} ({len(expected)} fields checked)")
        for m in mismatches:
            print("   ", m)

    conn.close()
    SMOKE_PATH.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print("\nAll outputs match the database:", all_ok)


if __name__ == "__main__":
    main()
