from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.oauth import local_redirect_uri
from app.scanner import DEFAULT_LOOKBACK_DAYS, run_scan, run_scan_range
from app.storage import (
    dashboard_stats,
    get_config,
    get_state,
    list_alerts,
    list_current_escalation_cases,
    list_events,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
RANGE_PRESETS = [
    {"days": 1, "label": "Today", "short": "Today"},
    {"days": 7, "label": "Last 7 days", "short": "7d"},
    {"days": 30, "label": "Last 30 days", "short": "30d"},
    {"days": 60, "label": "Last 60 days", "short": "60d"},
    {"days": 90, "label": "Last 90 days", "short": "90d"},
    {"days": 180, "label": "Last 6 months", "short": "6mo"},
    {"days": 365, "label": "Last year", "short": "1yr"},
]
METRIC_LABELS = {
    "": "Alerts",
    "total": "Alerts",
    "critical": "Critical clients",
    "repeated": "Repeated threats",
    "unresolved": "Unresolved alerts",
    "escalated": "Escalated alerts",
}


def _parse_payload(payload: str) -> dict:
    result: dict = {}
    for block in (payload or "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("**") and block.endswith("**"):
            title = block[2:-2]
            if " - " in title:
                result["threat"] = title.split(" - ", 1)[1]
        elif ": " in block:
            key, _, val = block.partition(": ")
            result[key.lower().replace(" ", "_")] = val.strip()
    return result


def _decode_reasons(value: object) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return [str(value)]
    if isinstance(loaded, list):
        return [str(item) for item in loaded]
    return [str(loaded)]


def _split_domain_user(value: object) -> tuple[str, str]:
    text = str(value or "").strip()
    if "\\" in text:
        domain, user = text.split("\\", 1)
        return domain.strip(), user.strip()
    if "@" in text:
        user, domain = text.split("@", 1)
        return domain.strip(), user.strip()
    return "", text


def _escalation_title(row: dict) -> str:
    severity = str(row.get("severity") or "Critical").strip().title()
    host = str(row.get("hostname") or row.get("computer_name") or "unknown host").strip()
    domain, user = _split_domain_user(row.get("username"))
    if user and domain:
        return f"{severity} Alert: {user} @ {domain}"
    if user:
        return f"{severity} Alert: {user}"
    if domain:
        return f"{severity} Alert: {host} @ {domain}"
    return f"{severity} Alert: {host}"


def _status_keyword(row: dict) -> str:
    text = " ".join(
        str(row.get(field) or "")
        for field in ("containment_status", "resolved_status", "action_taken")
    ).lower()
    if not text.strip():
        return ""
    keywords = (
        ("unresolved", ("unresolved", "not resolved")),
        ("failed", ("failed", "failure", "unable to", "not cleaned", "action required")),
        ("contained", ("contained", "containment")),
        ("quarantined", ("quarantined", "quarantine")),
        ("cleaned", ("cleaned",)),
        ("deleted", ("deleted", "delete")),
        ("removed", ("removed", "remove")),
        ("blocked", ("blocked",)),
        ("resolved", ("resolved",)),
        ("terminated", ("terminated",)),
    )
    for label, matches in keywords:
        if any(match in text for match in matches):
            return label.title()
    return str(
        row.get("containment_status")
        or row.get("resolved_status")
        or row.get("action_taken")
        or ""
    ).strip()


def _format_date_short(d: str) -> str:
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f"{dt:%b} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return d or ""


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


def _today_utc() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _range_start(days: int) -> str:
    today = _today_utc()
    if days <= 1:
        return today.date().isoformat()
    return (today - timedelta(days=days - 1)).date().isoformat()


def _safe_range_days(value: str) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LOOKBACK_DAYS
    allowed = {preset["days"] for preset in RANGE_PRESETS}
    return days if days in allowed else DEFAULT_LOOKBACK_DAYS


def _safe_metric(value: str) -> str:
    return value if value in METRIC_LABELS else ""


def _ensure_scan_coverage(days: int) -> tuple[bool, int]:
    desired_start = _range_start(days)
    today = _today_utc().date().isoformat()
    coverage_start = get_state("scan_coverage_start")
    coverage_end = get_state("scan_coverage_end")
    processed = 0
    scanned = False

    if not coverage_start:
        result = run_scan_range(desired_start, today)
        return True, result.get("processed", 0)

    if desired_start < coverage_start:
        previous_day = (
            datetime.strptime(coverage_start, "%Y-%m-%d") - timedelta(days=1)
        ).date().isoformat()
        result = run_scan_range(desired_start, previous_day)
        processed += result.get("processed", 0)
        scanned = True

    if not coverage_end or coverage_end < today:
        result = run_scan()
        processed += result.get("processed", 0)
        scanned = True

    return scanned, processed


@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request):
    config = asdict(get_config(include_secrets=False))
    active_days = _safe_range_days(request.query_params.get("range", str(DEFAULT_LOOKBACK_DAYS)))
    active_metric = _safe_metric(request.query_params.get("metric", ""))
    view_start = _range_start(active_days)
    view_end = _today_utc().date().isoformat()
    active_label = next(
        preset["label"] for preset in RANGE_PRESETS if preset["days"] == active_days
    )

    auto_scanned = False
    auto_processed = 0
    auto_scan_failed = False
    if config.get("oauth_account"):
        try:
            auto_scanned, auto_processed = _ensure_scan_coverage(active_days)
        except Exception:
            auto_scan_failed = True

    stats = dashboard_stats(start=view_start, end=view_end)
    stats["last_scan_display"] = _format_datetime(stats.get("last_scan_time"))
    stats["scan_range_display"] = active_label
    stats["coverage_start_display"] = _format_date_short(get_state("scan_coverage_start"))
    stats["coverage_end_display"] = _format_date_short(get_state("scan_coverage_end"))
    stats["poll_interval_seconds"] = config.get("poll_interval_seconds") or 60

    if active_metric == "escalated":
        recent_alerts = list_current_escalation_cases(500, start=view_start, end=view_end)
    else:
        recent_alerts = list_alerts(500, start=view_start, end=view_end, metric=active_metric)
    for alert in recent_alerts:
        alert["received_display"] = _format_datetime(alert.get("received_time"))
        alert["score_reasons_list"] = _decode_reasons(alert.get("score_reasons"))
        alert["status_display"] = _status_keyword(alert)
    teams_messages = list_current_escalation_cases(50, start=view_start, end=view_end)
    for message in teams_messages:
        message["created_display"] = _format_datetime(message.get("created_at"))
        message["reason_label"] = _escalation_title(message)
        message["domain"], message["user_display"] = _split_domain_user(message.get("username"))
        message["parsed"] = _parse_payload(message.get("payload", ""))
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "config": config,
            "stats": stats,
            "redirect_uri": local_redirect_uri(request),
            "recent_alerts": recent_alerts,
            "escalations": list_events("escalation", 15),
            "noise_events": list_events("noise", 15),
            "suppressed_events": list_events("suppressed", 15),
            "teams_messages": teams_messages,
            "view_start": view_start,
            "view_end": view_end,
            "active_days": active_days,
            "active_metric": active_metric,
            "metric_label": METRIC_LABELS[active_metric],
            "range_presets": RANGE_PRESETS,
            "auto_scanned": auto_scanned,
            "auto_processed": auto_processed,
            "auto_scan_failed": auto_scan_failed,
        },
    )
