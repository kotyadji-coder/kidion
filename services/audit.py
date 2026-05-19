"""
audit.py — Security audit logging for kidion.

Logs auth events, PII detections, crisis detections, moderation actions.
Stores minimal data — no raw message content, no PII.
Auto-cleanup of entries older than 90 days.
"""

import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("kidion")


def init_audit_table(conn: sqlite3.Connection) -> None:
    """Create audit_log table if it doesn't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL,
            event_type TEXT NOT NULL,
            user_id    INTEGER,
            child_id   INTEGER,
            ip         TEXT,
            details    TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp);
    """)


def log_event(
    conn: sqlite3.Connection,
    event_type: str,
    user_id: int | None = None,
    child_id: int | None = None,
    ip: str | None = None,
    details: str = "",
) -> None:
    """
    Insert an audit log entry.

    Event types:
        login_success, login_failed, pin_success, pin_failed,
        rate_limit_hit, pii_detected, crisis_detected,
        output_moderated, account_deleted, child_deleted,
        consent_given, consent_revoked, chat_cleared,
        message_reported, password_reset_requested
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO audit_log (timestamp, event_type, user_id, child_id, ip, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now, event_type, user_id, child_id, ip, details[:500]),
        )
        conn.commit()
    except Exception as e:
        logger.debug("Audit log error: %s", e)


def cleanup_old_audit_logs(conn: sqlite3.Connection, days: int = 90) -> int:
    """Delete audit entries older than N days. Returns count deleted."""
    try:
        cursor = conn.execute(
            "DELETE FROM audit_log WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return cursor.rowcount
    except Exception:
        return 0
