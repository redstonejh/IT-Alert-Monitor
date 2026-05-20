from datetime import datetime, timezone

from app.acronis_parser import is_acronis_message, parse_acronis_message, parse_acronis_messages
from app.acronis_scanner import _process_messages
from app.database import get_connection, init_db


def _message(subject: str, body: str) -> dict:
    return {
        "id": "acronis-1",
        "internetMessageId": "<acronis-1@test>",
        "receivedDateTime": datetime(2026, 5, 19, tzinfo=timezone.utc).isoformat(),
        "subject": "FW: " + subject,
        "from": {"emailAddress": {"address": "notifications@trustbiztech.com"}},
        "body": {"content": body},
    }


def test_parse_forwarded_acronis_backup_failed_subject_and_body():
    subject = (
        "BACKUP FAILED (group: Biztech > R Brown Construction)"
        "(backup account: AdminRBrown)(machine: BigR-NewPC)(plan: Nas Backup)"
    )
    body = f"""
    From: noreply-abc@cloud.acronis.com <noreply-abc@cloud.acronis.com>
    Subject: {subject}

    Backup failed

    BigR-NewPC

    Cannot connect to the machine where network share is located.

    Plan name
    Nas Backup

    Group
    Biztech > R Brown Construction

    Account
    backups@trustbiztech.com
    """

    alert = parse_acronis_message(_message(subject, body))

    assert alert.sender == "noreply-abc@cloud.acronis.com"
    assert alert.subject == subject
    assert alert.severity == "Error"
    assert alert.alert_type == "Backup failed"
    assert alert.device == "BigR-NewPC"
    assert alert.plan_name == "Nas Backup"
    assert alert.alert_group == "Biztech > R Brown Construction"
    assert alert.account == "AdminRBrown"


def test_parse_forwarded_acronis_daily_status_report():
    subject = (
        "DAILY STATUS REPORT ON May 19, 2026, 4:40:25 PM "
        "(group: Leon's Car Care) (Critical: 0, Error: 0, Warning: 1, Information: 0)"
    )
    body = f"""
    From: noreply-abc@cloud.acronis.com <noreply-abc@cloud.acronis.com>
    Subject: {subject}

    Warning

    The backup was canceled due to the closed backup window

    Device
    LEONS-SVR-01.leons.local

    Plan name
    Cloud Backup for LEONS-SVR-01

    Group
    Leon's Car Care

    Account
    Leon's Car Care
    """

    alert = parse_acronis_message(_message(subject, body))

    assert alert.severity == "Warning"
    assert alert.alert_type == "Daily status report"
    assert alert.device == "LEONS-SVR-01.leons.local"
    assert alert.plan_name == "Cloud Backup for LEONS-SVR-01"
    assert alert.alert_group == "Leon's Car Care"
    assert alert.account == "Leon's Car Care"


def test_parse_acronis_daily_status_offline_machine_target_schema():
    subject = (
        "DAILY STATUS REPORT ON May 19, 2026, 8:09:37 PM "
        "(group: Schmidbauer Lumber Company) "
        "(Critical: 1, Error: 0, Warning: 0, Information: 0)"
    )
    body = f"""
    From: noreply-abc@cloud.acronis.com <noreply-abc@cloud.acronis.com>
    Subject: {subject}

    Critical
    Machine is offline for more than 30 days
    May 19, 2026, 11:22:27 AM
    There has been no connection with machine 'SLI-OfficeMgr' for 30 days. Backups of this machine are stopped.
    Device SLI-OfficeMgr
    Group Schmidbauer Lumber Company
    Account Schmidbauer Lumber Company
    """

    alert = parse_acronis_message(_message(subject, body))

    assert alert.alert_date == "May 19, 2026, 11:22:27 AM"
    assert alert.alert_group == "Schmidbauer Lumber Company"
    assert alert.device == "SLI-OfficeMgr"
    assert alert.backup_failed is True
    assert alert.reason == "No connection for 30 days"
    assert alert.severity == "Critical"


def test_parse_flattened_daily_status_report_fields():
    subject = (
        "DAILY STATUS REPORT ON May 20, 2026, 11:04:30 AM "
        "(group: Biztech) (Critical: 1, Error: 0, Warning: 0, Information: 0)"
    )
    body = (
        f"From: noreply-abc@cloud.acronis.com <noreply-abc@cloud.acronis.com> ? "
        f"Subject: {subject} ? Manage data protection Active alerts ? "
        "May 20, 2026, 11:04:30 AM ? CRITICAL 1 ERROR 0 WARNING 0 INFORMATION 0 ? "
        "Critical ? Machine is offline for more than 30 days May 20, 2026, 6:42:52 AM ? "
        "There has been no connection with machine 'DESKTOP-ML81B8H' for 34 days. "
        "Backups of this machine are stopped. ? Device ? DESKTOP-ML81B8H "
        "Group ? Biztech Account ? Biztech View in web console ?"
    )

    alert = parse_acronis_message(_message(subject, body))

    assert alert.alert_date == "May 20, 2026, 6:42:52 AM"
    assert alert.alert_group == "Biztech"
    assert alert.device == "DESKTOP-ML81B8H"
    assert alert.backup_failed is True
    assert alert.reason == "No connection for 34 days"
    assert alert.severity == "Critical"


def test_parse_daily_status_report_multiple_alert_rows():
    subject = (
        "DAILY STATUS REPORT ON May 20, 2026, 10:42:38 AM "
        "(group: R Brown Construction) (Critical: 2, Error: 0, Warning: 0, Information: 0)"
    )
    body = (
        f"From: noreply-abc@cloud.acronis.com <noreply-abc@cloud.acronis.com> ? "
        f"Subject: {subject} ? Critical ? Backup failed May 19, 2026, 9:02:31 PM ? "
        "Cannot connect to the machine where network share is located. ? Device ? BigR-NewPC "
        "Plan name ? Nas Backup Group ? R Brown Construction Account ? R Brown Construction "
        "View in web console ? Backup failed May 18, 2026, 10:14:47 PM ? "
        "Cannot connect to the machine where network share '/1/BigR-NewPC.tibx' is located. ? "
        "Device ? BigR-NewPC Plan name ? Cloud Backup for R Brown NAS Data "
        "Group ? R Brown Construction Account ? R Brown Construction View in web console ?"
    )

    alerts = parse_acronis_messages(_message(subject, body))

    assert len(alerts) == 2
    assert alerts[0].message_id == "acronis-1"
    assert alerts[1].message_id == "acronis-1#2"
    assert [alert.alert_date for alert in alerts] == [
        "May 19, 2026, 9:02:31 PM",
        "May 18, 2026, 10:14:47 PM",
    ]
    assert [alert.plan_name for alert in alerts] == [
        "Nas Backup",
        "Cloud Backup for R Brown NAS Data",
    ]
    assert all(alert.severity == "Critical" for alert in alerts)


def test_acronis_relevance_accepts_forwarded_acronis_email():
    subject = (
        "BACKUP SUCCEEDED WITH WARNINGS (group: Biztech > Baywood Golf & Country Club)"
        "(backup account: AdminBGC)(machine: DATASERVER.baywoodgcc.local)"
        "(plan: Baywood-Cloud Server Backup)"
    )
    body = f"""
    From: noreply-abc@cloud.acronis.com <noreply-abc@cloud.acronis.com>
    Subject: {subject}

    Manage data protection

    Backup succeeded with warnings
    """

    assert is_acronis_message(_message(subject, body))


def test_acronis_relevance_rejects_unrelated_forwarded_email():
    subject = "Monthly invoice available"
    body = """
    From: billing@example.test <billing@example.test>
    Subject: Monthly invoice available

    Your invoice for managed services is attached.
    """

    assert not is_acronis_message(_message(subject, body))


def test_acronis_relevance_rejects_mailbox_test_to_acronis_display_name():
    subject = "test"
    body = """
    From: Gabriel Cabrera <gabriel@trustbiztech.com>
    To: Acronis Backup <backups@trustbiztech.com>
    Subject: test

    Test sent to backups@trustbiztech.com should arrive to notifications@trustbiztech.com
    """

    assert not is_acronis_message(_message(subject, body))


def test_acronis_scanner_skips_unrelated_forwarded_email(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()

    result = _process_messages(
        [
            _message(
                "Monthly invoice available",
                """
                From: billing@example.test <billing@example.test>
                Subject: Monthly invoice available

                Your invoice for managed services is attached.
                """,
            )
        ],
        "Test",
    )

    assert result["processed"] == 0
    assert result["skipped"] == 1
    with get_connection() as conn:
        alert_count = conn.execute("SELECT COUNT(*) AS c FROM acronis_alerts").fetchone()["c"]
    assert alert_count == 0
