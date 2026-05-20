import logging
from copy import copy
from datetime import datetime, timedelta, timezone

from app.acronis_parser import parse_acronis_message
from app.database import init_db
from app.graph_client import GraphClient
from app.storage import acronis_alert_exists, get_acronis_config, save_acronis_alert, update_state

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
        if not message_id or acronis_alert_exists(message_id):
            skipped += 1
            continue
        try:
            alert = parse_acronis_message(message)
        except Exception:
            parse_failed += 1
            logger.exception("Acronis parser failed for message id=%s", message_id)
            continue
        save_acronis_alert(alert)
        processed += 1

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
