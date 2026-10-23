import sqlite3
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscribers.db")

DEFAULT_USER_COLUMNS = "name,category,total,rii,qib,gmp,closing_date"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database schema if not already present, with migrations."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_active INTEGER DEFAULT 1,
                tab TEXT DEFAULT 'open',
                category TEXT DEFAULT 'all',
                min_gmp REAL DEFAULT 0.0,
                min_total REAL DEFAULT 0.0,
                min_rii REAL DEFAULT 0.0,
                columns TEXT DEFAULT 'name,category,total,rii,qib,gmp,closing_date',
                format TEXT DEFAULT 'card',
                frequency TEXT DEFAULT 'daily',
                preferred_time TEXT DEFAULT 'morning',
                last_sent_date TEXT DEFAULT NULL,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()

        # Check existing table columns for migration
        cursor.execute("PRAGMA table_info(subscribers)")
        existing_cols = {col["name"] for col in cursor.fetchall()}

        if "frequency" not in existing_cols:
            cursor.execute("ALTER TABLE subscribers ADD COLUMN frequency TEXT DEFAULT 'daily'")
        if "preferred_time" not in existing_cols:
            cursor.execute("ALTER TABLE subscribers ADD COLUMN preferred_time TEXT DEFAULT 'morning'")
        if "last_sent_date" not in existing_cols:
            cursor.execute("ALTER TABLE subscribers ADD COLUMN last_sent_date TEXT DEFAULT NULL")
        conn.commit()

def add_subscriber(chat_id: int, username: Optional[str] = "", first_name: Optional[str] = "") -> Dict[str, Any]:
    """Register or re-activate a subscriber. Returns their current profile."""
    init_db()
    now_str = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()

        if row is None:
            cursor.execute("""
                INSERT INTO subscribers (
                    chat_id, username, first_name, is_active,
                    tab, category, min_gmp, min_total, min_rii,
                    columns, format, frequency, preferred_time, last_sent_date,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, 'open', 'all', 0.0, 0.0, 0.0, ?, 'card', 'daily', 'morning', NULL, ?, ?)
            """, (chat_id, username or "", first_name or "", DEFAULT_USER_COLUMNS, now_str, now_str))
        else:
            cursor.execute("""
                UPDATE subscribers
                SET is_active = 1,
                    username = ?,
                    first_name = ?,
                    updated_at = ?
                WHERE chat_id = ?
            """, (username or row["username"], first_name or row["first_name"], now_str, chat_id))
        conn.commit()

    return get_subscriber(chat_id)

def remove_subscriber(chat_id: int) -> bool:
    """Deactivate a subscriber (unsubscribes from automated broadcasts)."""
    init_db()
    now_str = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM subscribers WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if not row:
            return False

        cursor.execute("""
            UPDATE subscribers
            SET is_active = 0, updated_at = ?
            WHERE chat_id = ?
        """, (now_str, chat_id))
        conn.commit()
        return True

def get_subscriber(chat_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve subscriber profile and settings by chat_id."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def update_subscriber(chat_id: int, **kwargs) -> Optional[Dict[str, Any]]:
    """Update subscriber settings (tab, category, min_gmp, min_total, columns, format, frequency, preferred_time, last_sent_date)."""
    init_db()
    allowed_fields = {
        "tab", "category", "min_gmp", "min_total", "min_rii",
        "columns", "format", "is_active", "frequency",
        "preferred_time", "last_sent_date"
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return get_subscriber(chat_id)

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [chat_id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE subscribers SET {set_clause} WHERE chat_id = ?", values)
        conn.commit()

    return get_subscriber(chat_id)

def record_sent(chat_id: int, sent_date_str: Optional[str] = None):
    """Mark that data has been dispatched to this user on a given date (defaults to today)."""
    if not sent_date_str:
        sent_date_str = date.today().isoformat()
    update_subscriber(chat_id, last_sent_date=sent_date_str)

def should_send_to_user(subscriber: Dict[str, Any], current_slot: str, today: Optional[date] = None) -> bool:
    """
    Check if a subscriber is scheduled to receive data at current_slot ('morning' or 'evening') on today.
    Handles:
      - preferred_time: 'morning' (6 AM) or 'evening' (6 PM)
      - frequency:
          'daily': every day
          'alternate': every 2 days (1 day gap)
          'thirdday': every 3 days (skipping two days in between)
    """
    if not subscriber.get("is_active"):
        return False

    pref_time = subscriber.get("preferred_time", "morning")
    if pref_time != current_slot:
        return False

    if today is None:
        today = date.today()

    last_sent_str = subscriber.get("last_sent_date")
    if not last_sent_str:
        return True  # Never sent before, send today!

    try:
        last_sent = datetime.strptime(last_sent_str[:10], "%Y-%m-%d").date()
    except Exception:
        return True

    days_diff = (today - last_sent).days
    if days_diff < 1:
        # Already received data today
        return False

    freq = subscriber.get("frequency", "daily")
    if freq == "alternate":
        return days_diff >= 2
    elif freq == "thirdday":
        return days_diff >= 3
    else:  # 'daily'
        return days_diff >= 1

def get_active_subscribers() -> List[Dict[str, Any]]:
    """Fetch all active subscribers."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscribers WHERE is_active = 1")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
