from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.company_abbreviations import abbreviate_company, company_full_name
from app.storage import (
    dashboard_stats,
    escalation_for_alert,
    get_alert,
    get_config,
    historical_matches,
    list_alerts,
    list_events,
    list_teams_messages,
)

router = APIRouter(prefix="/alerts")
templates = Jinja2Templates(directory="app/templates")


def _pacific_fallback(utc: datetime) -> datetime:
    year = utc.year

    def nth_sunday(y: int, month: int, n: int) -> datetime:
        first = datetime(y, month, 1, tzinfo=timezone.utc)
        days_to_sunday = (6 - first.weekday()) % 7
        return first + timedelta(days=days_to_sunday + 7 * (n - 1))

    dst_start = nth_sunday(year, 3, 2) + timedelta(hours=10)
    dst_end = nth_sunday(year, 11, 1) + timedelta(hours=9)
    offset = timedelta(hours=-7 if dst_start <= utc < dst_end else -8)
    return utc + offset


def _format_datetime(value: object) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        utc = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return text
    try:
        local = utc.astimezone(ZoneInfo("America/Los_Angeles"))
    except ZoneInfoNotFoundError:
        local = _pacific_fallback(utc)
    hour = local.hour % 12 or 12
    return f"{local:%m/%d/%y} {hour}:{local:%M %p}"


def _threat_type_display(row: dict) -> str:
    raw = str(row.get("raw_email_body") or "").replace("\xa0", " ")
    match = re.search(r"\bDetection type:\s*([^\r\n]+)", raw, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip().strip(".,;").title()
    threat = str(row.get("threat_name") or row.get("detection_name") or "").strip()
    if "/" in threat:
        return threat.split("/", 1)[0].strip().title()
    return ""


def _threat_method_display(row: dict) -> str:
    threat = str(row.get("threat_name") or row.get("detection_name") or "").strip()
    lower = threat.lower()
    method_map = (
        ("phishing", "Phishing"),
        ("redirector", "Redirect"),
        ("packed", "Packed"),
        ("downloader", "Downloader"),
        ("adware", "Adware"),
        ("fakealert", "FakeAlert"),
        ("exploit", "Exploit"),
        ("riskware", "Riskware"),
        ("trojan", "Trojan"),
        ("kryptik", "Kryptik"),
        ("script", "Script"),
    )
    for token, label in method_map:
        if token in lower:
            return label
    if "/" in threat:
        threat = threat.split("/", 1)[1]
    return re.split(r"[^A-Za-z0-9]+", threat, 1)[0].title() if threat else ""


def _status_keyword(row: dict) -> str:
    text = " ".join(
        str(row.get(field) or "")
        for field in ("containment_status", "resolved_status", "action_taken")
    ).lower()
    if not text.strip():
        return ""
    keywords = (
        ("Unresolved", ("unresolved", "not resolved")),
        ("Failed", ("failed", "failure", "unable to", "not cleaned", "action required")),
        ("Contained", ("contained", "containment")),
        ("Quarantined", ("quarantined", "quarantine")),
        ("Cleaned", ("cleaned",)),
        ("Deleted", ("deleted", "delete")),
        ("Removed", ("removed", "remove")),
        ("Blocked", ("blocked",)),
        ("Resolved", ("resolved",)),
        ("Terminated", ("terminated",)),
    )
    for label, matches in keywords:
        if any(match in text for match in matches):
            return label
    return str(
        row.get("containment_status")
        or row.get("resolved_status")
        or row.get("action_taken")
        or ""
    ).strip()


@router.get("")
def alerts(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "config": asdict(get_config(include_secrets=False)),
            "stats": dashboard_stats(),
            "recent_alerts": list_alerts(50),
            "escalations": list_events("escalation", 15),
            "noise_events": list_events("noise", 15),
            "suppressed_events": list_events("suppressed", 15),
            "teams_messages": list_teams_messages(15),
        },
    )


@router.get("/{alert_id}")
def alert_detail(request: Request, alert_id: int):
    alert = get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert["client_display"] = abbreviate_company(alert.get("client_name", ""))
    alert["client_full_display"] = company_full_name(alert.get("client_name", "") or alert.get("client_display", ""))
    alert["received_display"] = _format_datetime(alert.get("received_time"))
    alert["type_display"] = _threat_type_display(alert)
    alert["method_display"] = _threat_method_display(alert)
    alert["status_display"] = _status_keyword(alert)
    alert["endpoint_display"] = alert.get("hostname") or alert.get("computer_name") or "Unknown endpoint"
    matches = historical_matches(alert.get("hostname", ""), alert.get("threat_name", ""), alert_id)
    for match in matches:
        match["received_display"] = _format_datetime(match.get("received_time"))
    return templates.TemplateResponse(
        "alert_detail.html",
        {
            "request": request,
            "alert": alert,
            "escalation": escalation_for_alert(alert_id),
            "matches": matches,
        },
    )
