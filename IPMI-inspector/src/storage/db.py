"""IPMI Inspector local SQLite (reserved for future caches)."""

import sqlite3

DB_PATH = 'profiles.db'


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Ensure DB file exists; schema added when features need it."""
    global DB_PATH
    DB_PATH = db_path
    with get_connection() as conn:
        conn.execute('SELECT 1')
        conn.commit()
