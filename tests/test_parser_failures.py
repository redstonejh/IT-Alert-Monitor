from datetime import datetime, timezone

from app.database import get_connection, init_db
from app.scanner import _process_messages
from app.storage import get_state


def test_matching_email_missing_required_fields_records_parse_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    message = {
        "id": "missing-fields-1",
        "internetMessageId": "<missing-fields-1@test>",
        "receivedDateTime": datetime.now(timezone.utc).isoformat(),
        "subject": "ESET notification with malformed body",
        "from": {"emailAddress": {"address": "eset@example.test"}},
        "body": {"content": "This email has no alert fields."},
    }

    result = _process_messages([message], "Test")

    assert result["parse_failed"] == 1
    assert get_state("last_parse_failed_count") == "1"
    with get_connection() as conn:
        alert_count = conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
        event = conn.execute("SELECT event_type, message FROM events").fetchone()
    assert alert_count == 0
    assert event["event_type"] == "parse_failed"
    assert "missing threat_name, hostname" in event["message"]
