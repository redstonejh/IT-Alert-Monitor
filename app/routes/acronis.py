from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.storage import get_config, get_state

router = APIRouter()
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


@router.get("/acronis")
def acronis_dashboard(request: Request):
    config = asdict(get_config(include_secrets=False))
    last_scan_display = _format_datetime(get_state("last_scan_time"))
    return templates.TemplateResponse(
        "acronis_dashboard.html",
        {
            "request": request,
            "config": config,
            "last_scan_display": last_scan_display,
            "acronis_stats": {"critical": 0, "error": 0, "warning": 0, "information": 0},
            "acronis_alerts": [],
        },
    )
