import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.database import get_connection, init_db
from app.graph_client import GraphClient
from app.logger import setup_logging
from app.parser import parse_graph_message
from app.rules import evaluate_alert, record_escalation, should_send_escalation
from app.scoring import score_alert
from app.storage import (
    add_event,
    add_teams_message,
    alert_exists,
    get_config,
    get_state,
    save_alert,
    update_alert_escalation_reason,
    update_state,
)
from app.teams_notifier import TeamsNotifier

logger = logging.getLogger(__name__)
DEFAULT_LOOKBACK_DAYS = 60
DEFAULT_POLL_INTERVAL_SECONDS = 60
REQUIRED_PARSE_FIELDS = ("threat_name", "hostname")


def _date_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def _merge_coverage(start_date: str, end_date: str | None = None) -> None:
    start = start_date[:10]
    end = (end_date or _date_text(datetime.now(timezone.utc)))[:10]
    current_start = get_state("scan_coverage_start")
    current_end = get_state("scan_coverage_end")
    if not current_start or start < current_start:
        update_state("scan_coverage_start", start)
    if not current_end or end > current_end:
        update_state("scan_coverage_end", end)


def _process_messages(messages: list[dict], source: str) -> dict[str, int]:
    init_db()
    config = get_config()
    notifier = TeamsNotifier(config.teams_webhook_url)
    processed = skipped = escalated = noise = parse_failed = 0
    parse_failure_samples: list[str] = []

    for message in messages:
        message_id = message.get("id", "")
        if not message_id or alert_exists(message_id):
            skipped += 1
            continue
        try:
            alert = parse_graph_message(message)
        except Exception as exc:
            parse_failed += 1
            subject = message.get("subject", "No subject")
            parse_failure_samples.append(f"{subject}: {exc}")
            add_event(None, "parse_failed", f"{source}: {subject}: {exc}")
            logger.exception("Parser failed for message id=%s", message_id)
            continue
        missing_fields = [
            field for field in REQUIRED_PARSE_FIELDS if not getattr(alert, field, "")
        ]
        if missing_fields:
            parse_failed += 1
            subject = alert.subject or message.get("subject", "No subject")
            detail = f"missing {', '.join(missing_fields)}"
            parse_failure_samples.append(f"{subject}: {detail}")
            add_event(None, "parse_failed", f"{source}: {subject}: {detail}")
            skipped += 1
            continue
        score, label, reasons = score_alert(
            alert.threat_name, alert.hostname, alert.received_time,
            alert.action_taken, alert.containment_status, alert.resolved_status,
            config,
        )
        alert.severity = label
        alert.score = score
        alert.score_reasons = json.dumps(reasons)
        alert_id = save_alert(alert)
        if alert_id is None:
            skipped += 1
            continue
        processed += 1
        decision = evaluate_alert(alert, config)
        update_alert_escalation_reason(alert_id, decision.reason)
        if decision.should_alert:
            if should_send_escalation(decision, config):
                payload = notifier.format_alert(alert, decision.reason, decision.count)
                if config.teams_dry_run or not config.teams_webhook_url:
                    add_teams_message(alert_id, "preview", decision.reason, payload)
                    add_event(alert_id, "escalation", f"{decision.reason} (Teams local log)")
                    record_escalation(alert_id, decision)
                    escalated += 1
                else:
                    try:
                        notifier.send_text(payload)
                        add_teams_message(alert_id, "sent", decision.reason, payload)
                        add_event(alert_id, "escalation", decision.reason)
                        record_escalation(alert_id, decision)
                        update_state("last_teams_alert_time", datetime.now(timezone.utc).isoformat())
                        escalated += 1
                    except Exception as exc:
                        add_teams_message(alert_id, "failed", decision.reason, payload, str(exc))
                        add_event(alert_id, "teams_failed", decision.reason)
                        logger.exception("Teams send failed")
            else:
                add_event(alert_id, "suppressed", f"{decision.reason} (anti-spam)")
        else:
            add_event(alert_id, "noise", decision.reason)
            noise += 1

    update_state("last_scan_time", datetime.now(timezone.utc).isoformat())
    update_state("last_parse_failed_count", str(parse_failed))
    update_state("last_parse_failed_samples", json.dumps(parse_failure_samples[:5]))
    logger.info(
        "%s scan complete: processed=%s skipped=%s escalated=%s noise=%s parse_failed=%s",
        source,
        processed,
        skipped,
        escalated,
        noise,
        parse_failed,
    )
    return {
        "processed": processed,
        "skipped": skipped,
        "escalated": escalated,
        "noise": noise,
        "parse_failed": parse_failed,
    }


def backfill_severity(force: bool = False) -> int:
    """Re-parse action fields and re-score all alerts. Returns count updated."""
    from app.parser import FIELD_PATTERNS, _extract
    init_db()
    config = get_config()
    where = "" if force else "WHERE severity IS NULL OR severity = '' OR score = 0"
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, threat_name, hostname, received_time, action_taken, "
            f"containment_status, resolved_status, raw_email_body FROM alerts "
            f"{where} ORDER BY received_time ASC"
        ).fetchall()
    updated = 0
    for row in rows:
        try:
            received = datetime.fromisoformat(row["received_time"].replace("Z", "+00:00"))
            # Re-extract action fields from raw body using the latest parser patterns
            raw = row["raw_email_body"] or ""
            action_taken       = row["action_taken"]       or _extract(FIELD_PATTERNS["action_taken"], raw)
            containment_status = row["containment_status"] or _extract(FIELD_PATTERNS["containment_status"], raw)
            resolved_status    = row["resolved_status"]    or _extract(FIELD_PATTERNS["resolved_status"], raw)
            score, label, reasons = score_alert(
                row["threat_name"] or "",
                row["hostname"] or "",
                received,
                action_taken,
                containment_status,
                resolved_status,
                config,
            )
            with get_connection() as conn:
                conn.execute(
                    "UPDATE alerts SET severity = ?, score = ?, action_taken = ?, "
                    "containment_status = ?, resolved_status = ?, score_reasons = ?, "
                    "policy_version = ? WHERE id = ?",
                    (
                        label,
                        score,
                        action_taken,
                        containment_status,
                        resolved_status,
                        json.dumps(reasons),
                        "containment-v1",
                        row["id"],
                    ),
                )
            updated += 1
        except Exception:
            logger.exception("Backfill failed for alert id=%s", row["id"])
    if updated:
        logger.info("Backfilled severity scores for %s alerts", updated)
    return updated


def run_scan() -> dict[str, int]:
    init_db()
    config = get_config()
    if not config.lookback_days:
        config.lookback_days = DEFAULT_LOOKBACK_DAYS
    client = GraphClient(config)
    result = _process_messages(client.iter_matching_messages(), "Graph")
    start = config.start_date[:10] if config.start_date else _date_text(
        datetime.now(timezone.utc) - timedelta(days=config.lookback_days)
    )
    _merge_coverage(start)
    return result


def run_scan_range(start_date: str, end_date: str | None = None) -> dict[str, int]:
    init_db()
    from copy import copy
    from datetime import datetime, timezone
    config = copy(get_config())
    # Ensure full ISO datetime so Graph API accepts it
    if len(start_date) == 10:
        start_date = start_date + "T00:00:00Z"
    config.start_date = start_date
    config.lookback_days = 0
    client = GraphClient(config)
    messages = client.iter_matching_messages()
    if end_date:
        if len(end_date) == 10:
            end_date = end_date + "T23:59:59Z"
        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        messages = [
            m for m in messages
            if datetime.fromisoformat(
                m.get("receivedDateTime", "1970-01-01T00:00:00Z").replace("Z", "+00:00")
            ) <= end_dt
        ]
    result = _process_messages(messages, "Graph range")
    _merge_coverage(start_date, end_date)
    return result


def _sample_message(message_id: str, received: datetime, subject: str, body: str) -> dict:
    return {
        "id": message_id,
        "internetMessageId": f"<{message_id}@local.test>",
        "receivedDateTime": received.isoformat().replace("+00:00", "Z"),
        "subject": subject,
        "from": {"emailAddress": {"address": "eset-alerts@example.local"}},
        "body": {"contentType": "text", "content": body},
    }


def run_sample_scan() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    run_id = uuid4().hex[:8]
    messages = [
        _sample_message(
            f"sample-{run_id}-1",
            now - timedelta(hours=2),
            "ESET Threat Alert - Win32/TestThreat",
            """
            Client: Contoso
            Hostname: FINANCE-WS01
            Computer name: FINANCE-WS01
            Username: j.smith
            Threat name: Win32/TestThreat
            Detection name: Win32/TestThreat.A
            Severity: Medium
            Action taken: Cleaned
            Containment status: Contained
            Resolved status: Resolved
            Scan type: Real-time file system protection
            IP address: 10.10.4.25
            Operating system: Windows 11
            """,
        ),
        _sample_message(
            f"sample-{run_id}-2",
            now - timedelta(hours=1),
            "ESET Threat Alert - Win32/TestThreat",
            """
            Client: Contoso
            Hostname: FINANCE-WS01
            Username: j.smith
            Threat name: Win32/TestThreat
            Severity: Medium
            Action taken: Cleaned
            Containment status: Contained
            Resolved status: Resolved
            Scan type: Real-time file system protection
            IP address: 10.10.4.25
            Operating system: Windows 11
            """,
        ),
        _sample_message(
            f"sample-{run_id}-3",
            now,
            "ESET Critical Alert - Win32/TestThreat",
            """
            Client: Contoso
            Hostname: FINANCE-WS01
            Username: j.smith
            Threat name: Win32/TestThreat
            Severity: Critical
            Action taken: Remediation failed
            Containment status: Failed
            Resolved status: Unresolved
            Scan type: On-demand scanner
            IP address: 10.10.4.25
            Operating system: Windows 11
            """,
        ),
    ]
    return _process_messages(messages, "Sample")



def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ESET Outlook alert parser once.")
    parser.add_argument("--sample", action="store_true", help="Process generated sample ESET messages without Graph.")
    args = parser.parse_args()
    setup_logging()
    result = run_sample_scan() if args.sample else run_scan()
    print(result)


if __name__ == "__main__":
    main()
