from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.storage import get_state, get_xymon_config, list_xymon_alerts, xymon_dashboard_stats
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


@router.get("/xymon")
@router.get("/xymon/")
def xymon_dashboard(request: Request):
    xymon_config = get_xymon_config()
    active_days = _safe_range_days(request.query_params.get("range", str(DEFAULT_LOOKBACK_DAYS)))
    view_start = _range_start(active_days)
    view_end = _today_utc().date().isoformat()
    auto_scanned = False
    auto_processed = 0
    auto_scan_failed = False
    if xymon_config.mailbox_address:
        try:
            auto_scanned, auto_processed = _ensure_xymon_scan_coverage(active_days)
        except Exception:
            auto_scan_failed = True
    last_scan_display = _format_datetime(get_state("xymon_last_scan_time"))
    last_scan_error = get_state("xymon_last_scan_error")
    stats = xymon_dashboard_stats(start=view_start, end=view_end)
    raw_alerts = list_xymon_alerts(limit=200, start=view_start, end=view_end)
    alerts = []
    for row in raw_alerts:
        row["received_display"] = _format_datetime(row.get("received_time"))
        alerts.append(row)
    return templates.TemplateResponse(
        "xymon_dashboard.html",
        {
            "request": request,
            "xymon_config": xymon_config,
            "last_scan_display": last_scan_display,
            "last_scan_error": last_scan_error,
            "xymon_stats": stats,
            "xymon_alerts": alerts,
            "active_days": active_days,
            "range_presets": RANGE_PRESETS,
            "view_start": view_start,
            "view_end": view_end,
            "auto_scanned": auto_scanned,
            "auto_processed": auto_processed,
            "auto_scan_failed": auto_scan_failed,
        },
    )
