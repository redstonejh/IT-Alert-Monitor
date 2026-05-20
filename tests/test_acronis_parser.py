from datetime import datetime, timezone

from app.acronis_parser import parse_acronis_message


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
