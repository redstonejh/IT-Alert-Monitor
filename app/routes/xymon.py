from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.company_abbreviations import abbreviate_company
from app.storage import (
    get_config,
    get_setting,
    get_state,
    get_xymon_alert,
    get_xymon_config,
    list_xymon_alerts,
    xymon_dashboard_stats,
)
from app.xymon_scanner import DEFAULT_LOOKBACK_DAYS, run_xymon_scan, run_xymon_scan_range

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
    "red": "Red alerts",
    "yellow": "Yellow alerts",
    "purple": "Purple alerts",
    "green": "Green alerts",
}


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


def _sync_healthy(value: object, *, failed: bool = False, error: object = "") -> bool:
    if failed or error or not value:
        return False
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return False
    return True


def _format_date_compact(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%y")
    except (ValueError, TypeError):
        return value or ""


def _range_display(start: str, end: str) -> str:
    return f"{_format_date_compact(start)} - {_format_date_compact(end)}"


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


def _search_matches(query: str, values: list[object]) -> bool:
    terms = [term for term in re.split(r"\s+", query.strip().lower()) if term]
    if not terms:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return all(term in haystack for term in terms)


def _status_class(status: object) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"red", "yellow", "purple", "green"}:
        return f"sev-xymon-{normalized}"
    return "sev-unknown"


def _status_display(status: object) -> str:
    return str(status or "").strip().title() or "Unknown"


def _ensure_xymon_scan_coverage(days: int) -> tuple[bool, int]:
    desired_start = _range_start(days)
    today = _today_utc().date().isoformat()
    coverage_start = get_state("xymon_scan_coverage_start")
    coverage_end = get_state("xymon_scan_coverage_end")
    processed = 0
    scanned = False

    if not coverage_start:
        result = run_xymon_scan_range(desired_start, today)
        return bool(result.get("scan_attempted")), result.get("processed", 0)

    if desired_start < coverage_start:
        previous_day = (
            datetime.strptime(coverage_start, "%Y-%m-%d") - timedelta(days=1)
        ).date().isoformat()
        result = run_xymon_scan_range(desired_start, previous_day)
        processed += result.get("processed", 0)
        scanned = scanned or bool(result.get("scan_attempted"))

    if not coverage_end or coverage_end < today:
        result = run_xymon_scan()
        processed += result.get("processed", 0)
        scanned = scanned or bool(result.get("scan_attempted"))

    return scanned, processed


def _mailbox_checks(xymon_config) -> dict[str, bool]:
    return {
        "tenant_id": bool(xymon_config.tenant_id),
        "client_id": bool(xymon_config.client_id),
        "secret_id": bool(get_setting("xymon_client_secret")),
        "teams_webhook": bool(get_config().teams_webhook_url or get_setting("teams_webhook_url")),
    }


@router.get("/xymon")
@router.get("/xymon/")
def xymon_dashboard(request: Request):
    xymon_config = get_xymon_config()
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
    if xymon_config.mailbox_address:
        try:
            auto_scanned, auto_processed = _ensure_xymon_scan_coverage(coverage_days)
        except Exception:
            auto_scan_failed = True
    last_scan_time = get_state("xymon_last_scan_time")
    last_scan_display = _format_datetime(last_scan_time)
    last_scan_error = get_state("xymon_last_scan_error")
    sync_failed = bool(auto_scan_failed or request.query_params.get("scan_failed") or last_scan_error)
    sync_healthy = _sync_healthy(last_scan_time, failed=sync_failed, error=last_scan_error)
    stats = xymon_dashboard_stats(start=view_start, end=view_end)
    raw_alerts = list_xymon_alerts(limit=200, start=view_start, end=view_end, status=active_metric)
    alerts = []
    for row in raw_alerts:
        row["received_display"] = _format_datetime(row.get("received_time"))
        row["status_display"] = _status_display(row.get("status"))
        row["status_class"] = _status_class(row.get("status"))
        if search_query and not _search_matches(
            search_query,
            [
                row.get("received_display"),
                row.get("host"),
                row.get("test_name"),
                row.get("status_display"),
                row.get("message"),
                row.get("age"),
                row.get("group_name"),
                row.get("subject"),
                row.get("sender"),
                row.get("raw_payload"),
            ],
        ):
            continue
        alerts.append(row)
    return templates.TemplateResponse(
        "xymon_dashboard.html",
        {
            "request": request,
            "xymon_config": xymon_config,
            "mailbox_checks": _mailbox_checks(xymon_config),
            "last_scan_display": last_scan_display,
            "last_scan_error": last_scan_error,
            "sync_failed": sync_failed,
            "sync_healthy": sync_healthy,
            "xymon_stats": stats,
            "xymon_alerts": alerts,
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


@router.get("/xymon/alerts/{alert_id}")
def xymon_alert_detail(request: Request, alert_id: int):
    alert = get_xymon_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Xymon alert not found")
    alert["received_display"] = _format_datetime(alert.get("received_time"))
    alert["status_display"] = _status_display(alert.get("status"))
    alert["status_class"] = _status_class(alert.get("status"))
    alert["group_display"] = abbreviate_company(alert.get("group_name", ""))
    return templates.TemplateResponse(
        "xymon_alert_detail.html",
        {
            "request": request,
            "alert": alert,
        },
    )
