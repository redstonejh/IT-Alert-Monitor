from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

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
    return templates.TemplateResponse(
        "alert_detail.html",
        {
            "request": request,
            "alert": alert,
            "escalation": escalation_for_alert(alert_id),
            "matches": historical_matches(alert.get("hostname", ""), alert.get("threat_name", ""), alert_id),
        },
    )
