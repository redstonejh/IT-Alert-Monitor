from datetime import datetime, timedelta, timezone

from app.database import get_connection
from app.models import AppConfig, EscalationDecision, ParsedAlert

REASON_LABELS: dict[str, str] = {
    "critical_severity":                   "First critical alert for client",
    "same_threat_same_host_repeated":      "Same threat repeated on the same host",
    "same_threat_same_host_multiple_days": "Same threat persisting across multiple days",
    "same_host_multiple_threats_24h":      "Multiple different threats on the same host (24 h)",
    "same_threat_multiple_endpoints":      "Same threat spreading across multiple endpoints",
    "noise":                               "No escalation",
}


def reason_label(reason: str) -> str:
    return REASON_LABELS.get(reason, reason.replace("_", " ").title())


def client_key(alert: ParsedAlert) -> str:
    value = alert.client_name or alert.hostname or alert.computer_name or "unknown-client"
    return " ".join(value.lower().strip().split())


def evaluate_alert(alert: ParsedAlert, config: AppConfig) -> EscalationDecision:
    """Escalate only the first critical alert per client in a 24-hour window."""
    if (alert.severity or "").lower() != "critical":
        return EscalationDecision(False, "noise", "", 0, 1)
    fingerprint = f"critical_client_24h|{client_key(alert)}"
    return EscalationDecision(True, "critical_severity", fingerprint, 4, 1)


def should_send_escalation(decision: EscalationDecision, config: AppConfig) -> bool:
    """Allow at most one escalation per client fingerprint per 24 hours."""
    window_start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_alerted_at FROM escalations WHERE fingerprint = ?",
            (decision.fingerprint,),
        ).fetchone()
    if row is None:
        return True
    last_alerted = row["last_alerted_at"]
    if not last_alerted:
        return True
    return datetime.fromisoformat(last_alerted) <= datetime.fromisoformat(window_start)


def record_escalation(alert_id: int, decision: EscalationDecision) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO escalations(alert_id, fingerprint, reason, last_count, last_severity_rank, last_alerted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                alert_id = excluded.alert_id,
                reason = excluded.reason,
                last_count = excluded.last_count,
                last_severity_rank = excluded.last_severity_rank,
                last_alerted_at = excluded.last_alerted_at
            """,
            (alert_id, decision.fingerprint, decision.reason, decision.count, decision.severity_rank, now),
        )
