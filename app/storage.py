from dataclasses import fields
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from app.config import get_app_settings
from app.database import get_connection
from app.models import AppConfig, AcronisConfig, ParsedAlert, ParsedAcronisAlert
from app.security import SecretStore

SENSITIVE_KEYS = {"client_secret", "teams_webhook_url", "oauth_token_cache", "oauth_flow"}
STATUS_SQL = (
    "LOWER(COALESCE(action_taken, '') || ' ' || "
    "COALESCE(containment_status, '') || ' ' || COALESCE(resolved_status, ''))"
)


def _env_overrides(config: AppConfig) -> AppConfig:
    env = get_app_settings()
    config.tenant_id = env.graph_tenant_id or config.tenant_id
    config.client_id = env.graph_client_id or config.client_id
    config.client_secret = env.graph_client_secret or config.client_secret
    config.mailbox_address = env.graph_mailbox_address or config.mailbox_address
    config.mail_folder = env.graph_mail_folder or config.mail_folder
    config.teams_webhook_url = env.teams_webhook_url or config.teams_webhook_url
    config.poll_interval_seconds = env.poll_interval_seconds or config.poll_interval_seconds
    return config


def get_config(include_secrets: bool = True) -> AppConfig:
    secret_store = SecretStore()
    config = AppConfig()
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value, sensitive FROM settings").fetchall()
    for row in rows:
        value = secret_store.decrypt(row["value"]) if row["sensitive"] else row["value"]
        if value is not None and hasattr(config, row["key"]):
            current = getattr(config, row["key"])
            if isinstance(current, bool):
                value = str(value).lower() in {"1", "true", "yes", "on"}
            elif isinstance(current, int):
                value = int(value)
            setattr(config, row["key"], value)
    config = _env_overrides(config)
    if not include_secrets:
        config.client_secret = ""
        config.teams_webhook_url = ""
    return config


def save_config(form_data: dict[str, Any]) -> None:
    secret_store = SecretStore()
    valid_fields = {field.name for field in fields(AppConfig)}
    with get_connection() as conn:
        for key, value in form_data.items():
            if key not in valid_fields:
                continue
            if key in SENSITIVE_KEYS and not value:
                continue
            sensitive = 1 if key in SENSITIVE_KEYS else 0
            stored_value = secret_store.encrypt(str(value)) if sensitive else str(value)
            conn.execute(
                """
                INSERT INTO settings(key, value, sensitive)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, sensitive = excluded.sensitive
                """,
                (key, stored_value, sensitive),
            )


def get_setting(key: str, decrypt: bool = True) -> str:
    secret_store = SecretStore()
    with get_connection() as conn:
        row = conn.execute("SELECT value, sensitive FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return ""
    if row["sensitive"] and decrypt:
        return secret_store.decrypt(row["value"]) or ""
    return row["value"]


def save_setting(key: str, value: str, sensitive: bool = False) -> None:
    secret_store = SecretStore()
    stored_value = secret_store.encrypt(value) if sensitive else value
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, sensitive)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, sensitive = excluded.sensitive
            """,
            (key, stored_value, 1 if sensitive else 0),
        )


ACRONIS_SENSITIVE_KEYS = {"acronis_client_secret"}


def get_acronis_config() -> AcronisConfig:
    return AcronisConfig(
        tenant_id=get_setting("acronis_tenant_id"),
        client_id=get_setting("acronis_client_id"),
        client_secret=get_setting("acronis_client_secret"),
        mailbox_address=get_setting("acronis_mailbox_address"),
        mail_folder=get_setting("acronis_mail_folder"),
        sender_filter=get_setting("acronis_sender_filter"),
        subject_filter=get_setting("acronis_subject_filter"),
        lookback_days=int(get_setting("acronis_lookback_days") or "60"),
    )


def save_acronis_config(data: dict) -> None:
    for key, value in data.items():
        if not key.startswith("acronis_"):
            continue
        if key in ACRONIS_SENSITIVE_KEYS and not value:
            continue
        save_setting(key, str(value), sensitive=(key in ACRONIS_SENSITIVE_KEYS))


def acronis_alert_exists(message_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM acronis_alerts WHERE message_id = ?", (message_id,)
        ).fetchone()
    return row is not None


def save_acronis_alert(alert: ParsedAcronisAlert) -> None:
    data = alert.as_dict()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    with get_connection() as conn:
        try:
            conn.execute(
                f"INSERT INTO acronis_alerts({columns}) VALUES ({placeholders})",
                tuple(data.values()),
            )
        except Exception:
            pass


def list_acronis_alerts(limit: int = 200) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM acronis_alerts ORDER BY received_time DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def acronis_dashboard_stats() -> dict[str, int]:
    with get_connection() as conn:
        def _count(where: str) -> int:
            return conn.execute(
                f"SELECT COUNT(*) AS c FROM acronis_alerts {where}"
            ).fetchone()["c"]
        return {
            "critical": _count("WHERE LOWER(severity) = 'critical'"),
            "error": _count("WHERE LOWER(severity) = 'error'"),
            "warning": _count("WHERE LOWER(severity) = 'warning'"),
            "information": _count("WHERE LOWER(severity) = 'information'"),
        }


def delete_setting(key: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def alert_exists(message_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM alerts WHERE message_id = ?", (message_id,)).fetchone()
    return row is not None


def save_alert(alert: ParsedAlert) -> int | None:
    data = alert.as_dict()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                f"INSERT INTO alerts({columns}) VALUES ({placeholders})",
                tuple(data.values()),
            )
        except Exception:
            return None
        return int(cursor.lastrowid)


def update_alert_escalation_reason(alert_id: int, reason: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE alerts SET escalation_reason = ? WHERE id = ?",
            (reason, alert_id),
        )


def get_alert(alert_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    return dict(row) if row else None


def list_alerts(
    limit: int = 25,
    start: str = "",
    end: str = "",
    metric: str = "",
) -> list[dict[str, Any]]:
    conds: list[str] = []
    params: list[Any] = []
    if start:
        conds.append("received_time >= ?")
        params.append(f"{start}T00:00:00" if len(start) == 10 else start)
    if end:
        conds.append("received_time <= ?")
        params.append(f"{end}T23:59:59" if len(end) == 10 else end)
    if metric == "critical":
        conds.append("LOWER(severity) = 'critical'")
    elif metric == "unresolved":
        conds.append(
            f"({STATUS_SQL} LIKE '%failed%' OR {STATUS_SQL} LIKE '%unresolved%' "
            f"OR {STATUS_SQL} LIKE '%not resolved%' OR {STATUS_SQL} LIKE '%not cleaned%' "
            f"OR {STATUS_SQL} LIKE '%action required%')"
        )
    elif metric == "repeated":
        repeated_range = ""
        if start:
            repeated_range += " AND repeated_alerts.received_time >= ?"
            params.append(f"{start}T00:00:00" if len(start) == 10 else start)
        if end:
            repeated_range += " AND repeated_alerts.received_time <= ?"
            params.append(f"{end}T23:59:59" if len(end) == 10 else end)
        conds.append(
            f"""
            EXISTS (
                SELECT 1 FROM alerts repeated_alerts
                WHERE repeated_alerts.hostname = alerts.hostname
                  AND repeated_alerts.threat_name = alerts.threat_name
                  AND repeated_alerts.hostname != ''
                  AND repeated_alerts.threat_name != ''
                  {repeated_range}
                GROUP BY repeated_alerts.hostname, repeated_alerts.threat_name
                HAVING COUNT(*) >= 3
            )
            """
        )
    elif metric == "escalated":
        conds.append("LOWER(severity) = 'critical'")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY received_time DESC LIMIT ?", params
        ).fetchall()
    return [dict(row) for row in rows]


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _client_identity(row: dict[str, Any]) -> str:
    return str(
        row.get("client_name")
        or row.get("hostname")
        or row.get("computer_name")
        or "unknown-client"
    ).strip().lower()


def list_current_escalation_cases(limit: int = 25, start: str = "", end: str = "") -> list[dict[str, Any]]:
    conds = ["LOWER(severity) = 'critical'"]
    params: list[Any] = []
    if start:
        conds.append("received_time >= ?")
        params.append(f"{start}T00:00:00" if len(start) == 10 else start)
    if end:
        conds.append("received_time <= ?")
        params.append(f"{end}T23:59:59" if len(end) == 10 else end)
    where = "WHERE " + " AND ".join(conds)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY received_time ASC",
            params,
        ).fetchall()

    cases: list[dict[str, Any]] = []
    last_by_client: dict[str, datetime] = {}
    for row in rows:
        item = dict(row)
        client = _client_identity(item)
        received = _parse_dt(item["received_time"])
        last_sent = last_by_client.get(client)
        if last_sent and received < last_sent + timedelta(hours=24):
            continue
        last_by_client[client] = received
        item["reason"] = "critical_severity"
        if item.get("escalation_reason"):
            item["reason"] = item["escalation_reason"]
        item["status"] = "current_policy"
        item["payload"] = ""
        item["alert_id"] = item["id"]
        item["created_at"] = item["received_time"]
        cases.append(item)

    return list(reversed(cases))[:limit]


def list_events(event_type: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    sql = "SELECT events.*, alerts.hostname, alerts.threat_name, alerts.severity FROM events LEFT JOIN alerts ON alerts.id = events.alert_id"
    params: tuple[Any, ...] = ()
    if event_type:
        sql += " WHERE event_type = ?"
        params = (event_type,)
    sql += " ORDER BY events.created_at DESC LIMIT ?"
    params += (limit,)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def add_event(alert_id: int | None, event_type: str, message: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO events(alert_id, event_type, message) VALUES (?, ?, ?)",
            (alert_id, event_type, message),
        )


def add_teams_message(
    alert_id: int | None,
    status: str,
    reason: str,
    payload: str,
    error: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO teams_messages(alert_id, status, reason, payload, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert_id, status, reason, payload, error),
        )


def list_teams_messages(limit: int = 25, start: str = "", end: str = "") -> list[dict[str, Any]]:
    conds: list[str] = []
    params: list[Any] = []
    if start:
        conds.append("alerts.received_time >= ?")
        params.append(f"{start}T00:00:00" if len(start) == 10 else start)
    if end:
        conds.append("alerts.received_time <= ?")
        params.append(f"{end}T23:59:59" if len(end) == 10 else end)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT teams_messages.*, alerts.hostname, alerts.computer_name, alerts.client_name,
                   alerts.threat_name, alerts.severity, alerts.received_time
            FROM teams_messages
            LEFT JOIN alerts ON alerts.id = teams_messages.alert_id
            {where}
            {"AND" if where else "WHERE"} teams_messages.reason = 'critical_severity'
              AND LOWER(alerts.severity) = 'critical'
            ORDER BY teams_messages.created_at DESC
            """,
            params,
        ).fetchall()
    messages: list[dict[str, Any]] = []
    seen_client_days: set[str] = set()
    for row in rows:
        item = dict(row)
        client = (
            item.get("client_name")
            or item.get("hostname")
            or item.get("computer_name")
            or "unknown-client"
        )
        date_key = str(item.get("received_time") or item.get("created_at") or "")[:10]
        key = f"{str(client).strip().lower()}|{date_key}"
        if key in seen_client_days:
            continue
        seen_client_days.add(key)
        messages.append(item)
        if len(messages) >= limit:
            break
    return messages


def update_state(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO scanner_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_state(key: str) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM scanner_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def dashboard_stats(start: str = "", end: str = "") -> dict[str, Any]:
    # Build an AND-able date filter for alerts queries
    date_conds: list[str] = []
    date_params: list[Any] = []
    if start:
        date_conds.append("received_time >= ?")
        date_params.append(f"{start}T00:00:00" if len(start) == 10 else start)
    if end:
        date_conds.append("received_time <= ?")
        date_params.append(f"{end}T23:59:59" if len(end) == 10 else end)
    df = (" AND " + " AND ".join(date_conds)) if date_conds else ""

    with get_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM alerts WHERE 1=1{df}", date_params
        ).fetchone()["c"]
        critical = conn.execute(
            f"""
            SELECT COUNT(DISTINCT LOWER(TRIM(
                COALESCE(NULLIF(client_name, ''), NULLIF(hostname, ''), NULLIF(computer_name, ''), 'unknown-client')
            ))) AS c
            FROM alerts
            WHERE LOWER(severity) = 'critical'{df}
            """,
            date_params,
        ).fetchone()["c"]
        repeated = conn.execute(
            f"""
            SELECT COUNT(*) AS c FROM (
                SELECT hostname, threat_name FROM alerts
                WHERE hostname != '' AND threat_name != ''{df}
                GROUP BY hostname, threat_name HAVING COUNT(*) >= 3
            )
            """,
            date_params,
        ).fetchone()["c"]
        failed = conn.execute(
            f"""
            SELECT COUNT(*) AS c FROM alerts
            WHERE ({STATUS_SQL} LIKE '%failed%' OR {STATUS_SQL} LIKE '%unresolved%'
            OR {STATUS_SQL} LIKE '%not resolved%' OR {STATUS_SQL} LIKE '%not cleaned%'
            OR {STATUS_SQL} LIKE '%action required%'){df}
            """,
            date_params,
        ).fetchone()["c"]
        dry_runs = conn.execute(
            "SELECT COUNT(*) AS c FROM teams_messages WHERE status IN ('dry_run', 'preview')"
        ).fetchone()["c"]
        last_teams_message = conn.execute(
            "SELECT created_at FROM teams_messages ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return {
        "total": total,
        "critical": critical,
        "repeated": repeated,
        "failed": failed,
        "teams_logged": len(list_current_escalation_cases(10000, start=start, end=end)),
        "dry_runs": dry_runs,
        "last_scan_time": get_state("last_scan_time"),
        "last_parse_failed_count": int(get_state("last_parse_failed_count") or 0),
        "last_parse_failed_samples": json.loads(get_state("last_parse_failed_samples") or "[]"),
        "last_teams_alert_time": get_state("last_teams_alert_time"),
        "last_teams_message_time": last_teams_message["created_at"] if last_teams_message else "",
        "scan_range_label": get_state("last_scan_range_label"),
        "scan_range_start": get_state("last_scan_range_start"),
        "scan_range_end": get_state("last_scan_range_end"),
    }


def historical_matches(hostname: str, threat_name: str, exclude_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM alerts
            WHERE id != ? AND hostname = ? AND threat_name = ?
            ORDER BY received_time DESC LIMIT 50
            """,
            (exclude_id, hostname, threat_name),
        ).fetchall()
    return [dict(row) for row in rows]


def escalation_for_alert(alert_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM escalations WHERE alert_id = ? ORDER BY last_alerted_at DESC LIMIT 1",
            (alert_id,),
        ).fetchone()
    return dict(row) if row else None
