from urllib.parse import quote
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse

from app.database import get_connection
from app.graph_client import GraphClient
from app.models import ParsedAlert
from app.scanner import backfill_severity, run_sample_scan, run_scan, run_scan_range
from app.storage import add_teams_message, get_config, update_state
from app.teams_notifier import TeamsNotifier

router = APIRouter(prefix="/actions")


def _ok(message: str, detail: object | None = None) -> dict:
    return {"ok": True, "message": message, "detail": detail}


@router.post("/test-graph")
def test_graph():
    try:
        GraphClient(get_config()).test_connection()
        return _ok("Microsoft Graph token and tenant connection succeeded.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-mailbox")
def test_mailbox():
    try:
        GraphClient(get_config()).test_mailbox()
        return _ok("Mailbox access succeeded.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-teams")
def test_teams():
    try:
        config = get_config()
        message = "ESET alert parser test notification."
        if config.teams_dry_run or not config.teams_webhook_url:
            add_teams_message(None, "preview", "test_notification", message)
            return _ok("Teams test logged locally.")
        result = TeamsNotifier(config.teams_webhook_url).send_text(message)
        add_teams_message(None, "sent", "test_notification", message)
        return _ok(
            "Teams webhook test sent and logged.",
            {"status_code": result.status_code, "response": result.response_text},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-critical")
def test_critical():
    try:
        config = get_config()
        alert = ParsedAlert(
            message_id="teams-critical-test",
            internet_message_id="<teams-critical-test@local>",
            received_time=datetime.now(timezone.utc),
            subject="ESET Critical Test Alert",
            sender="local-test",
            client_name="Test Client",
            hostname="TEST-ENDPOINT-01",
            username="test.user",
            threat_name="Test/Critical.Eicar",
            detection_name="Test/Critical.Eicar",
            severity="Critical",
            action_taken="Remediation failed",
            containment_status="Failed",
            resolved_status="Unresolved",
            scan_type="Teams delivery test",
            raw_email_body="Generated local Teams critical test.",
        )
        notifier = TeamsNotifier(config.teams_webhook_url)
        message = notifier.format_alert(alert, "critical_severity", 1)
        if config.teams_dry_run or not config.teams_webhook_url:
            add_teams_message(None, "preview", "critical_test", message)
            return _ok("Critical test logged locally. Turn off local preview mode and save to post to Teams.")
        result = notifier.send_text(message)
        add_teams_message(None, "sent", "critical_test", message)
        return _ok(
            "Critical test sent to Teams.",
            {"status_code": result.status_code, "response": result.response_text},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-parser")
def run_parser_now():
    try:
        return _ok("Parser run completed.", run_scan())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-sample")
def run_sample_parser():
    try:
        return _ok("Sample parser run completed.", run_sample_scan())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/scan-inbox")
def scan_inbox():
    """Scan the mailbox with the default configured lookback (no date range)."""
    try:
        result = run_scan()
        return RedirectResponse(
            f"/dashboard?scanned={result.get('processed', 0)}&view_all=1",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(f"/dashboard?scan_failed=1&err={quote(str(exc))}&view_all=1", status_code=303)


@router.post("/scan-range")
def scan_range(start_date: str = Form(...), end_date: str = Form(""), range_label: str = Form("")):
    try:
        result = run_scan_range(start_date, end_date or None)
        view_end = (end_date or start_date)[:10]
        update_state("last_scan_range_start", start_date[:10])
        update_state("last_scan_range_end", view_end)
        update_state("last_scan_range_label", range_label)
        return RedirectResponse(
            f"/dashboard?scanned={result.get('processed', 0)}"
            f"&view_start={start_date[:10]}&view_end={view_end}&view_label={quote(range_label)}",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(f"/dashboard?scan_failed=1&err={quote(str(exc))}", status_code=303)


@router.post("/rescore")
def rescore_all():
    updated = backfill_severity(force=True)
    return RedirectResponse(f"/dashboard?rescored={updated}", status_code=303)


@router.post("/clear-and-rescan")
def clear_and_rescan():
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM alerts")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM teams_messages")
            conn.execute("DELETE FROM escalations")
        update_state("last_scan_range_start", "")
        update_state("last_scan_range_end", "")
        update_state("last_scan_range_label", "")
        result = run_scan()
        return RedirectResponse(
            f"/dashboard?scanned={result.get('processed', 0)}&view_all=1",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(f"/dashboard?scan_failed=1&err={quote(str(exc))}", status_code=303)
