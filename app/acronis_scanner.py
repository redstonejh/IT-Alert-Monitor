import logging
from copy import copy
from datetime import datetime, timedelta, timezone

from app.acronis_parser import is_acronis_message, parse_acronis_messages
from app.database import init_db
from app.graph_client import GraphClient
from app.storage import (
    acronis_alert_exists,
    acronis_escalation_recent,
    add_teams_message,
    get_acronis_config,
    get_config,
    list_acronis_alerts,
    record_acronis_escalation,
    save_acronis_alert,
    update_state,
)
from app.teams_notifier import TeamsNotifier

logger = logging.getLogger(__name__)
DEFAULT_LOOKBACK_DAYS = 60
PARSING_ENABLED = True


def _date_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def _merge_coverage(start_date: str, end_date: str | None = None) -> None:
    start = start_date[:10]
    end = (end_date or _date_text(datetime.now(timezone.utc)))[:10]
    from app.storage import get_state

    current_start = get_state("acronis_scan_coverage_start")
    current_end = get_state("acronis_scan_coverage_end")
    if not current_start or start < current_start:
        update_state("acronis_scan_coverage_start", start)
    if not current_end or end > current_end:
        update_state("acronis_scan_coverage_end", end)


def _configured(config) -> bool:
    if getattr(config, "auth_mode", "app") == "delegated":
        return bool(config.client_id and config.mailbox_address)
    return bool(config.tenant_id and config.client_id and config.client_secret and config.mailbox_address)


def _acronis_push_fingerprint(row: dict) -> str:
    company = str(row.get("company_display") or row.get("alert_group") or row.get("account") or "unknown").strip().lower()
    machine = str(row.get("machine_display") or row.get("device") or "unknown").strip().lower()
    return f"acronis_critical_24h|{company}|{machine}"


def _maybe_escalate_acronis_alert(alert_id: int) -> bool:
    from app.routes.acronis import (
        _acronis_triage_config,
        _backup_failed_display,
        _backup_failed_value,
        _company_display,
        _derived_severity_from_triage,
        _machine_display,
        _reason_display,
        _status_display,
        _triage_context,
        _triage_decision,
    )

    shared_config = get_config()
    rows = list_acronis_alerts(limit=500)
    target: dict | None = None
    for row in rows:
        row["company_display"] = _company_display(row)
        row["machine_display"] = _machine_display(row)
        row["backup_failed_display"] = _backup_failed_display(_backup_failed_value(row))
        row["reason_display"] = _reason_display(row)
        row["severity_display"] = _status_display(row)
        if int(row.get("id") or 0) == int(alert_id):
            target = row
    if not target:
        return False

    triage_config = _acronis_triage_config()
    context = _triage_context(rows)
    triage = _triage_decision(target, context, triage_config)
    severity_display, _severity_class = _derived_severity_from_triage(triage, triage_config)
    target["triage_score"] = triage["score"]
    target["triage_category_label"] = triage["category_label"]
    target["derived_severity_display"] = severity_display
    if severity_display.lower() != "critical":
        return False

    fingerprint = _acronis_push_fingerprint(target)
    if acronis_escalation_recent(fingerprint, cooldown_hours=24):
        return False

    notifier = TeamsNotifier(shared_config.teams_webhook_url)
    payload = notifier.format_acronis_alert(target, "critical_severity", 1)
    if shared_config.teams_dry_run or not shared_config.teams_webhook_url:
        status = "preview"
        add_teams_message(None, status, "acronis_critical_severity", payload)
        record_acronis_escalation(alert_id, fingerprint, "critical_severity", status, payload)
        return True

    try:
        notifier.send_text(payload)
        add_teams_message(None, "sent", "acronis_critical_severity", payload)
        record_acronis_escalation(alert_id, fingerprint, "critical_severity", "sent", payload)
        update_state("last_acronis_teams_alert_time", datetime.now(timezone.utc).isoformat())
        return True
    except Exception as exc:
        add_teams_message(None, "failed", "acronis_critical_severity", payload, str(exc))
        record_acronis_escalation(alert_id, fingerprint, "critical_severity", "failed", payload, str(exc))
        logger.exception("Acronis Teams send failed")
        return False


def _process_messages(messages: list[dict], source: str) -> dict[str, int]:
    processed = skipped = parse_failed = 0
    if not PARSING_ENABLED:
        update_state("acronis_last_scan_time", datetime.now(timezone.utc).isoformat())
        logger.info("%s Acronis scan complete: parsing disabled", source)
        return {
            "processed": 0,
            "skipped": len(messages),
            "parse_failed": 0,
            "scan_attempted": True,
        }
    for message in messages:
        message_id = message.get("id", "")
        if not message_id:
            skipped += 1
            continue
        if not is_acronis_message(message):
            skipped += 1
            continue
        try:
            alerts = parse_acronis_messages(message)
        except Exception:
            parse_failed += 1
            logger.exception("Acronis parser failed for message id=%s", message_id)
            continue
        for alert in alerts:
            was_new = not acronis_alert_exists(alert.message_id)
            alert_id = save_acronis_alert(alert)
            if was_new:
                processed += 1
                _maybe_escalate_acronis_alert(alert_id)
            else:
                skipped += 1

    update_state("acronis_last_scan_time", datetime.now(timezone.utc).isoformat())
    logger.info(
        "%s Acronis scan complete: processed=%s skipped=%s parse_failed=%s",
        source,
        processed,
        skipped,
        parse_failed,
    )
    return {
        "processed": processed,
        "skipped": skipped,
        "parse_failed": parse_failed,
        "scan_attempted": True,
    }


def run_acronis_scan() -> dict[str, int]:
    init_db()
    config = get_acronis_config()

    if not _configured(config):
        logger.info("Acronis scanner: credentials not configured, skipping")
        return {"processed": 0, "skipped": 0, "parse_failed": 0, "scan_attempted": False}
    if not config.lookback_days:
        config.lookback_days = DEFAULT_LOOKBACK_DAYS

    client = GraphClient(config)
    try:
        messages = client.iter_matching_messages()
    except Exception:
        logger.exception("Acronis Graph scan failed")
        update_state("acronis_last_scan_error", "Sign in with Microsoft from ESET Settings to refresh mailbox access.")
        return {"processed": 0, "skipped": 0, "parse_failed": 0, "scan_attempted": False}

    result = _process_messages(messages, "Graph")
    update_state("acronis_last_scan_error", "")
    start = config.start_date[:10] if config.start_date else _date_text(
        datetime.now(timezone.utc) - timedelta(days=config.lookback_days)
    )
    _merge_coverage(start)
    return result


def run_acronis_scan_range(start_date: str, end_date: str | None = None) -> dict[str, int]:
    init_db()
    config = copy(get_acronis_config())
    if not _configured(config):
        logger.info("Acronis scanner: credentials not configured, skipping range scan")
        return {"processed": 0, "skipped": 0, "parse_failed": 0, "scan_attempted": False}
    if len(start_date) == 10:
        start_date = start_date + "T00:00:00Z"
    config.start_date = start_date
    config.lookback_days = 0
    client = GraphClient(config)
    try:
        messages = client.iter_matching_messages()
    except Exception:
        logger.exception("Acronis Graph range scan failed")
        update_state("acronis_last_scan_error", "Sign in with Microsoft from ESET Settings to refresh mailbox access.")
        return {"processed": 0, "skipped": 0, "parse_failed": 0, "scan_attempted": False}

    if end_date:
        if len(end_date) == 10:
            end_date = end_date + "T23:59:59Z"
        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        messages = [
            message for message in messages
            if datetime.fromisoformat(
                message.get("receivedDateTime", "1970-01-01T00:00:00Z").replace("Z", "+00:00")
            ) <= end_dt
        ]
    result = _process_messages(messages, "Graph range")
    update_state("acronis_last_scan_error", "")
    _merge_coverage(start_date, end_date)
    return result
