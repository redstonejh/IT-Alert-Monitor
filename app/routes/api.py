from dataclasses import asdict
from datetime import datetime, timezone
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.routes.dashboard import (
    RANGE_PRESETS,
    METRIC_LABELS,
    _format_datetime,
    _escalation_title,
    _range_start,
    _safe_metric,
    _safe_range_days,
    _split_domain_user,
    _today_utc,
)
from app.scoring import scoring_breakdown
from app.storage import (
    dashboard_stats,
    escalation_for_alert,
    get_alert,
    get_config,
    historical_matches,
    list_alerts,
    list_current_escalation_cases,
)

router = APIRouter(prefix="/api")


PREVIEW_CONFIG_FIELDS = {
    "use_taxonomy_weighting",
    "unknown_base_score",
    "severity_critical_threshold",
    "severity_high_threshold",
    "severity_medium_threshold",
    "repeated_same_host_window_hours",
    "repeated_same_host_1_adjustment",
    "repeated_same_host_2_adjustment",
    "repeated_same_host_3_adjustment",
    "campaign_endpoint_window_hours",
    "campaign_endpoint_2_adjustment",
    "campaign_endpoint_3_adjustment",
    "campaign_endpoint_5_adjustment",
    "persistence_2_day_adjustment",
    "persistence_4_day_adjustment",
    "velocity_window_hours",
    "velocity_baseline_days",
    "velocity_multiplier",
    "velocity_min_count",
    "velocity_adjustment",
    "host_alert_window_hours",
    "host_alert_count_threshold",
    "host_alert_adjustment",
    "failure_adjustment",
    "success_adjustment",
    "taxonomy_scores",
}


def _decode_reasons(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return [str(value)]
    if isinstance(loaded, list):
        return [str(item) for item in loaded]
    return [str(loaded)]


def _public_alert(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["received_display"] = _format_datetime(item.get("received_time"))
    item["score_reasons"] = _decode_reasons(item.get("score_reasons"))
    item["reason_label"] = _escalation_title(item)
    item["domain"], item["user_display"] = _split_domain_user(item.get("username"))
    return item


@router.get("/dashboard")
def dashboard_data(request: Request) -> dict[str, Any]:
    active_days = _safe_range_days(request.query_params.get("range", "60"))
    active_metric = _safe_metric(request.query_params.get("metric", ""))
    view_start = _range_start(active_days)
    view_end = _today_utc().date().isoformat()
    stats = dashboard_stats(start=view_start, end=view_end)

    if active_metric == "escalated":
        recent = list_current_escalation_cases(500, start=view_start, end=view_end)
    else:
        recent = list_alerts(500, start=view_start, end=view_end, metric=active_metric)

    return {
        "config": asdict(get_config(include_secrets=False)),
        "stats": stats,
        "alerts": [_public_alert(alert) for alert in recent],
        "teams_messages": [
            _public_alert(message)
            for message in list_current_escalation_cases(50, start=view_start, end=view_end)
        ],
        "range": {
            "active_days": active_days,
            "active_metric": active_metric,
            "metric_label": METRIC_LABELS[active_metric],
            "view_start": view_start,
            "view_end": view_end,
            "presets": RANGE_PRESETS,
        },
    }


@router.get("/alerts/{alert_id}")
def alert_data(alert_id: int) -> dict[str, Any]:
    alert = get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "alert": _public_alert(alert),
        "escalation": escalation_for_alert(alert_id),
        "matches": [_public_alert(row) for row in historical_matches(
            alert.get("hostname", ""),
            alert.get("threat_name", ""),
            alert_id,
        )],
    }


@router.get("/settings")
def settings_data() -> dict[str, Any]:
    config = asdict(get_config(include_secrets=False))
    return {"config": config}


@router.post("/scoring-preview")
async def scoring_preview(request: Request) -> dict[str, Any]:
    payload = await request.json()
    config = get_config()
    preview_config = payload.get("config") or {}
    for key, value in preview_config.items():
        if key not in PREVIEW_CONFIG_FIELDS or not hasattr(config, key):
            continue
        current = getattr(config, key)
        if isinstance(current, bool):
            setattr(config, key, str(value).lower() in {"1", "true", "yes", "on"})
        elif isinstance(current, int):
            try:
                setattr(config, key, int(value))
            except (TypeError, ValueError):
                pass
        else:
            setattr(config, key, str(value))
    received_text = payload.get("received_time") or ""
    try:
        received = (
            datetime.fromisoformat(str(received_text).replace("Z", "+00:00"))
            if received_text
            else datetime.now(timezone.utc)
        )
    except ValueError:
        received = datetime.now(timezone.utc)
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    return scoring_breakdown(
        str(payload.get("threat_name") or ""),
        str(payload.get("hostname") or ""),
        received,
        str(payload.get("action_taken") or ""),
        str(payload.get("containment_status") or ""),
        str(payload.get("resolved_status") or ""),
        config,
    )
