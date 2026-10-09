"""Reset the working database to a fresh copy of the original.

Overwrites data/campus_customs_new.db with data/campus_customs.db.
The original database is only read, never modified.

Usage:
    python reset_db.py
"""

import shutil
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
ORIGINAL_DB = DATA_DIR / "campus_customs.db"
WORKING_DB = DATA_DIR / "campus_customs_new.db"


def reset_db() -> Path:
    if not ORIGINAL_DB.exists():
        raise FileNotFoundError(f"Original database not found: {ORIGINAL_DB}")

    # Remove stale SQLite side files so they don't get replayed onto the fresh copy.
    for suffix in ("-wal", "-shm", "-journal"):
        side_file = WORKING_DB.with_name(WORKING_DB.name + suffix)
        side_file.unlink(missing_ok=True)

    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    return WORKING_DB


if __name__ == "__main__":
    path = reset_db()
    print(f"Reset complete: {path.name} is now a fresh copy of {ORIGINAL_DB.name}")
