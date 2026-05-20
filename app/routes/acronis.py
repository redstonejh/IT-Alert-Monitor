from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.acronis_scanner import DEFAULT_LOOKBACK_DAYS, run_acronis_scan, run_acronis_scan_range
from app.company_abbreviations import abbreviate_company
from app.storage import get_acronis_alert, get_acronis_config, get_state, list_acronis_alerts

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
    "critical": "Critical alerts",
    "error": "Error alerts",
    "warning": "Warning alerts",
    "information": "Information alerts",
}
_ACRONIS_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M\b",
    flags=re.IGNORECASE,
)


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


def _format_date_compact(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%y")
    except (ValueError, TypeError):
        return value or ""


def _range_display(start: str, end: str) -> str:
    return f"{_format_date_compact(start)} - {_format_date_compact(end)}"


def _severity_class(severity: object) -> str:
    normalized = str(severity or "unknown").strip().lower()
    return {
        "critical": "critical",
        "error": "high",
        "warning": "medium",
        "information": "low",
        "info": "low",
    }.get(normalized, "unknown")


def _severity_display(severity: object) -> str:
    normalized = str(severity or "").strip().lower()
    return {
        "critical": "Critical",
        "error": "Error",
        "warning": "Warning",
        "information": "Information",
        "info": "Information",
    }.get(normalized, str(severity or "Unknown").strip().title() or "Unknown")


def _backup_failed_display(value: object) -> str:
    if isinstance(value, str):
        return "Fail" if value.strip().lower() in {"1", "true", "yes", "y"} else "Pass"
    return "Fail" if value else "Pass"


def _search_matches(query: str, values: list[object]) -> bool:
    terms = [term for term in re.split(r"\s+", query.strip().lower()) if term]
    if not terms:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return all(term in haystack for term in terms)


def _raw_text(row: dict) -> str:
    return re.sub(r"\s+", " ", str(row.get("raw_email_body") or "").replace("\xa0", " ")).strip()


def _label_value(label: str, text: str) -> str:
    stop_labels = (
        "Plan name",
        "Where to back up",
        "Group",
        "Account",
        "View in web console",
        "If you have",
        "Subject",
        "From",
        "To",
        "Sent",
    )
    stop = "|".join(re.escape(item) for item in stop_labels if item.lower() != label.lower())
    match = re.search(
        rf"\b{re.escape(label)}\b\s+(.+?)(?=\s+(?:{stop})\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().strip(".,;")
    return ""


def _company_display(row: dict) -> str:
    text = _raw_text(row)
    company = str(
        row.get("alert_group")
        or row.get("account")
        or _label_value("Group", text)
        or _label_value("Account", text)
        or "Unknown"
    ).strip()
    return abbreviate_company(company)


def _alert_date_display(row: dict) -> str:
    parsed = _alert_event_datetime(row)
    if parsed:
        hour = parsed.hour % 12 or 12
        return f"{parsed:%m/%d/%y} {hour}:{parsed:%M %p}"
    return str(row.get("received_display") or row.get("received_time") or "").strip()


def _alert_event_datetime(row: dict) -> datetime | None:
    text = _raw_text(row)
    body_dates = [
        match.group(0) for match in _ACRONIS_DATE_RE.finditer(text)
    ]
    alert_date = body_dates[-1] if body_dates else ""
    display = str(row.get("alert_date") or alert_date or "").strip()
    if display:
        try:
            return datetime.strptime(display, "%B %d, %Y, %I:%M:%S %p")
        except ValueError:
            return None
    return None


def _row_in_event_range(row: dict, start: str, end: str) -> bool:
    event_dt = _alert_event_datetime(row)
    if not event_dt:
        return True
    event_date = event_dt.date().isoformat()
    return (not start or event_date >= start) and (not end or event_date <= end)


def _acronis_stats_from_rows(rows: list[dict]) -> dict[str, int]:
    stats = {"critical": 0, "error": 0, "warning": 0, "information": 0}
    for row in rows:
        severity = _status_display(row).strip().lower()
        if severity in stats:
            stats[severity] += 1
    return stats


def _machine_display(row: dict) -> str:
    text = _raw_text(row)
    quoted = re.search(r"machine\s+'([^']+)'", text, flags=re.IGNORECASE)
    return str(
        row.get("device")
        or _label_value("Device", text)
        or (quoted.group(1).strip() if quoted else "")
        or "Unknown"
    ).strip()


def _backup_failed_value(row: dict) -> bool:
    value = row.get("backup_failed")
    if isinstance(value, str) and value.strip():
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if value:
        return True
    text = "\n".join(str(row.get(field) or "") for field in ("alert_type", "reason", "raw_email_body")).lower()
    return any(
        marker in text
        for marker in (
            "backup failed",
            "backups of this machine are stopped",
            "backups are stopped",
            "backup is stopped",
            "failed",
            "missed",
            "unsuccessful",
            "unavailable",
            "blocked",
        )
    )


def _reason_display(row: dict) -> str:
    if row.get("reason"):
        return str(row["reason"]).strip()
    text = _raw_text(row)
    no_connection = re.search(r"no connection(?: with machine '[^']+')? for (\d+) days", text, flags=re.IGNORECASE)
    if no_connection:
        return f"No connection for {no_connection.group(1)} days"
    offline = re.search(r"offline for (?:more than )?(\d+) days", text, flags=re.IGNORECASE)
    if offline:
        return f"No connection for {offline.group(1)} days"
    canceled = re.search(r"backup was canceled due to (.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if canceled:
        return f"Backup canceled due to {canceled.group(1).strip()}"
    backup_failed = re.search(
        r"Backup failed\s+" + _ACRONIS_DATE_RE.pattern + r"\s+(.+?)(?=\s+Device\b|\s+Plan name\b|\s+Group\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if backup_failed:
        return backup_failed.group(1).strip().strip(".")
    return str(row.get("alert_type") or "").strip()


def _status_display(row: dict) -> str:
    text = _raw_text(row)
    match = re.search(
        r"\b(Critical|Error|Warning|Information)\b\s+(?:Backup failed|Machine is offline|The backup)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).capitalize()
    return _severity_display(row.get("severity"))


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


def _custom_range(start_value: str, end_value: str) -> tuple[str, str] | None:
    if not start_value or not end_value:
        return None
    try:
        start = datetime.strptime(start_value, "%Y-%m-%d").date()
        end = datetime.strptime(end_value, "%Y-%m-%d").date()
    except ValueError:
        return None
    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _safe_metric(value: str) -> str:
    return value if value in METRIC_LABELS else ""


def _ensure_acronis_scan_coverage(days: int) -> tuple[bool, int]:
    desired_start = _range_start(days)
    today = _today_utc().date().isoformat()
    coverage_start = get_state("acronis_scan_coverage_start")
    coverage_end = get_state("acronis_scan_coverage_end")
    processed = 0
    scanned = False

    if not coverage_start:
        result = run_acronis_scan_range(desired_start, today)
        return bool(result.get("scan_attempted")), result.get("processed", 0)

    if desired_start < coverage_start:
        previous_day = (
            datetime.strptime(coverage_start, "%Y-%m-%d") - timedelta(days=1)
        ).date().isoformat()
        result = run_acronis_scan_range(desired_start, previous_day)
        processed += result.get("processed", 0)
        scanned = scanned or bool(result.get("scan_attempted"))

    if not coverage_end or coverage_end < today:
        result = run_acronis_scan()
        processed += result.get("processed", 0)
        scanned = scanned or bool(result.get("scan_attempted"))

    return scanned, processed


@router.get("/acronis")
def acronis_dashboard(request: Request):
    acronis_config = get_acronis_config()
    active_days = _safe_range_days(request.query_params.get("range", str(DEFAULT_LOOKBACK_DAYS)))
    active_metric = _safe_metric(request.query_params.get("metric", ""))
    search_query = request.query_params.get("q", "").strip()
    custom_range = _custom_range(request.query_params.get("start", ""), request.query_params.get("end", ""))
    if custom_range:
        view_start, view_end = custom_range
        range_query = f"start={view_start}&end={view_end}"
        coverage_days = max(1, (_today_utc().date() - datetime.strptime(view_start, "%Y-%m-%d").date()).days + 1)
    else:
        view_start = _range_start(active_days)
        view_end = _today_utc().date().isoformat()
        range_query = f"range={active_days}"
        coverage_days = active_days
    auto_scanned = False
    auto_processed = 0
    auto_scan_failed = False
    if acronis_config.mailbox_address:
        try:
            auto_scanned, auto_processed = _ensure_acronis_scan_coverage(coverage_days)
        except Exception:
            auto_scan_failed = True
    last_scan_display = _format_datetime(get_state("acronis_last_scan_time"))
    last_scan_error = get_state("acronis_last_scan_error")
    raw_alerts = [
        row for row in list_acronis_alerts(limit=500, start=view_start, end=view_end)
        if _row_in_event_range(row, view_start, view_end)
    ]
    stats = _acronis_stats_from_rows(raw_alerts)
    alerts = []
    for row in raw_alerts:
        row_status = _status_display(row)
        if active_metric and row_status.lower() != active_metric:
            continue
        row["received_display"] = _format_datetime(row.get("received_time"))
        row["date_display"] = _alert_date_display(row)
        row["company_display"] = _company_display(row)
        row["machine_display"] = _machine_display(row)
        row["backup_failed_display"] = _backup_failed_display(_backup_failed_value(row))
        row["reason_display"] = _reason_display(row)
        row["severity_display"] = row_status
        row["severity_class"] = _severity_class(row["severity_display"])
        if search_query and not _search_matches(
            search_query,
            [
                row.get("received_display"),
                row.get("date_display"),
                row.get("company_display"),
                row.get("machine_display"),
                row.get("backup_failed_display"),
                row.get("reason_display"),
                row.get("severity_display"),
                row.get("alert_group"),
                row.get("account"),
                row.get("device"),
                row.get("plan_name"),
                row.get("alert_date"),
                row.get("subject"),
                row.get("sender"),
                row.get("raw_email_body"),
            ],
        ):
            continue
        alerts.append(row)
    return templates.TemplateResponse(
        "acronis_dashboard.html",
        {
            "request": request,
            "acronis_config": acronis_config,
            "last_scan_display": last_scan_display,
            "last_scan_error": last_scan_error,
            "acronis_stats": stats,
            "acronis_alerts": alerts,
            "active_days": active_days,
            "active_metric": active_metric,
            "search_query": search_query,
            "custom_range": bool(custom_range),
            "range_query": range_query,
            "range_display": _range_display(view_start, view_end),
            "metric_label": METRIC_LABELS[active_metric],
            "range_presets": RANGE_PRESETS,
            "view_start": view_start,
            "view_end": view_end,
            "auto_scanned": auto_scanned,
            "auto_processed": auto_processed,
            "auto_scan_failed": auto_scan_failed,
        },
    )


@router.get("/acronis/alerts/{alert_id}")
def acronis_alert_detail(request: Request, alert_id: int):
    alert = get_acronis_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Acronis alert not found")
    alert["received_display"] = _format_datetime(alert.get("received_time"))
    alert["date_display"] = _alert_date_display(alert)
    alert["company_display"] = _company_display(alert)
    alert["backup_failed_display"] = _backup_failed_display(alert.get("backup_failed"))
    alert["severity_class"] = _severity_class(alert.get("severity"))
    alert["severity_display"] = _severity_display(alert.get("severity"))
    return templates.TemplateResponse(
        "acronis_alert_detail.html",
        {
            "request": request,
            "alert": alert,
        },
    )
