import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import get_app_settings


def get_db_path() -> str:
    settings = get_app_settings()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return settings.database_path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                sensitive INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                internet_message_id TEXT,
                received_time TEXT NOT NULL,
                subject TEXT,
                sender TEXT,
                client_name TEXT,
                hostname TEXT,
                computer_name TEXT,
                username TEXT,
                threat_name TEXT,
                detection_name TEXT,
                severity TEXT,
                action_taken TEXT,
                containment_status TEXT,
                resolved_status TEXT,
                scan_type TEXT,
                ip_address TEXT,
                operating_system TEXT,
                raw_email_body TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_alert_identity
                ON alerts(hostname, threat_name, received_time);
            CREATE INDEX IF NOT EXISTS idx_alert_received_time
                ON alerts(received_time);

            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER,
                fingerprint TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                last_count INTEGER NOT NULL DEFAULT 0,
                last_severity_rank INTEGER NOT NULL DEFAULT 0,
                last_alerted_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(alert_id) REFERENCES alerts(id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(alert_id) REFERENCES alerts(id)
            );

            CREATE TABLE IF NOT EXISTS teams_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(alert_id) REFERENCES alerts(id)
            );

            CREATE TABLE IF NOT EXISTS scanner_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acronis_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                internet_message_id TEXT,
                received_time TEXT NOT NULL,
                subject TEXT,
                sender TEXT,
                severity TEXT,
                alert_type TEXT,
                device TEXT,
                plan_name TEXT,
                alert_group TEXT,
                account TEXT,
                raw_email_body TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_acronis_received_time
                ON acronis_alerts(received_time);
            """
        )
        # Migrate: add score column to existing databases
        try:
            conn.execute("ALTER TABLE alerts ADD COLUMN score INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists
        for column_sql in (
            "ALTER TABLE alerts ADD COLUMN score_reasons TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE alerts ADD COLUMN escalation_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE alerts ADD COLUMN policy_version TEXT NOT NULL DEFAULT 'containment-v1'",
        ):
            try:
                conn.execute(column_sql)
            except Exception:
                pass  # column already exists
