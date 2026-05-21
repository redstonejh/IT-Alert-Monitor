from app.routes.acronis import _derived_severity_from_triage, _triage_context, _triage_decision


def _row(reason: str, machine: str = "DESKTOP-123", severity: str = "Critical") -> dict:
    return {
        "company_display": "BT",
        "machine_display": machine,
        "backup_failed": 1,
        "backup_failed_display": "Fail",
        "reason_display": reason,
        "reason": reason,
        "severity": severity,
        "severity_display": severity,
        "alert_type": "Backup failed",
        "subject": "Acronis alert",
        "raw_email_body": reason,
    }


def test_acronis_triage_drive_failure_is_push_candidate():
    rows = [_row("Drive failure detected: SMART disk health failed", machine="BT-SERVER01")]
    context = _triage_context(rows)

    decision = _triage_decision(rows[0], context)

    assert decision["would_push"] is True
    assert decision["label"] == "Escalate"
    assert decision["category"] == "storage_failure"
    assert _derived_severity_from_triage(decision) == ("Critical", "critical")


def test_acronis_triage_stale_offline_workstation_is_noise():
    rows = [_row("No connection for 34 days", machine="DESKTOP-ML81B8H")]
    context = _triage_context(rows)

    decision = _triage_decision(rows[0], context)

    assert decision["would_push"] is False
    assert decision["label"] == "Suppress noise"
    assert decision["category"] == "stale_offline"
    assert _derived_severity_from_triage(decision) == ("Low", "low")


def test_acronis_triage_repeated_generic_failure_is_review_not_push():
    rows = [
        _row("The activity has failed due to runtime error", machine="BT-SERVER01"),
        _row("The activity has failed due to runtime error", machine="BT-SERVER01"),
    ]
    context = _triage_context(rows)

    decision = _triage_decision(rows[0], context)

    assert decision["would_push"] is False
    assert decision["label"] == "Dashboard only"
    assert decision["category"] == "backup_failed_generic"


def test_acronis_triage_new_generic_server_failure_is_review_not_push():
    rows = [_row("The activity has failed due to runtime error", machine="BT-SERVER01")]
    context = _triage_context(rows)

    decision = _triage_decision(rows[0], context)

    assert decision["would_push"] is False
    assert decision["label"] == "Review"
    assert decision["category"] == "backup_failed_generic"
    assert _derived_severity_from_triage(decision) == ("High", "high")


def test_acronis_triage_os_restart_is_not_review_worthy():
    rows = [
        _row(
            "The activity has failed due to restart of the operating system.",
            machine="BT-SERVER01",
        )
    ]
    context = _triage_context(rows)

    decision = _triage_decision(rows[0], context)

    assert decision["would_push"] is False
    assert decision["label"] in {"Dashboard only", "Suppress noise"}
    assert decision["category"] == "transient_maintenance"
