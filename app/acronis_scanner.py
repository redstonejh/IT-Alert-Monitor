import logging
from datetime import datetime, timezone

from app.acronis_parser import parse_acronis_message
from app.database import init_db
from app.graph_client import GraphClient
from app.storage import acronis_alert_exists, get_acronis_config, save_acronis_alert, update_state

logger = logging.getLogger(__name__)
DEFAULT_LOOKBACK_DAYS = 60


def run_acronis_scan() -> dict[str, int]:
    init_db()
    config = get_acronis_config()

    if not config.client_id or not config.mailbox_address:
        logger.info("Acronis scanner: credentials not configured, skipping")
        return {"processed": 0, "skipped": 0, "parse_failed": 0}
    if not config.lookback_days:
        config.lookback_days = DEFAULT_LOOKBACK_DAYS

    client = GraphClient(config)
    try:
        messages = client.iter_matching_messages()
    except Exception:
        logger.exception("Acronis Graph scan failed")
        return {"processed": 0, "skipped": 0, "parse_failed": 0}

    processed = skipped = parse_failed = 0
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
        "Acronis scan complete: processed=%s skipped=%s parse_failed=%s",
        processed,
        skipped,
        parse_failed,
    )
    return {"processed": processed, "skipped": skipped, "parse_failed": parse_failed}
