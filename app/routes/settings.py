from dataclasses import asdict

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import DEFAULT_TAXONOMY_SCORES
from app.routes.dashboard import _format_datetime
from app.scanner import backfill_severity, run_scan
from app.security import mask_secret
from app.storage import delete_setting, get_config, get_state, save_config

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def settings_page(request: Request):
    config = get_config()
    display = asdict(config)
    display["client_secret_masked"] = mask_secret(config.client_secret)
    display["teams_webhook_url_masked"] = mask_secret(config.teams_webhook_url)
    display["client_secret"] = ""
    display["teams_webhook_url"] = ""
    display["last_scan_display"] = _format_datetime(get_state("last_scan_time"))
    return templates.TemplateResponse("settings.html", {"request": request, "config": display})


@router.post("")
def save_settings(
    tenant_id: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    mailbox_address: str = Form(""),
    mail_folder: str = Form(""),
    teams_webhook_url: str = Form(""),
    teams_dry_run: bool = Form(False),
    escalation_cooldown_hours: int = Form(24),
    eset_sender_filter: str = Form(""),
    eset_subject_filter: str = Form("ESET"),
    taxonomy_scores: str = Form(""),
    use_taxonomy_weighting: bool = Form(False),
    unknown_base_score: int = Form(30),
    scoring_preset: str = Form("containment"),
    severity_critical_threshold: int = Form(95),
    severity_high_threshold: int = Form(70),
    severity_medium_threshold: int = Form(45),
    repeated_same_host_window_hours: int = Form(24),
    repeated_same_host_1_adjustment: int = Form(20),
    repeated_same_host_2_adjustment: int = Form(40),
    repeated_same_host_3_adjustment: int = Form(60),
    campaign_endpoint_window_hours: int = Form(24),
    campaign_endpoint_2_adjustment: int = Form(8),
    campaign_endpoint_3_adjustment: int = Form(18),
    campaign_endpoint_5_adjustment: int = Form(30),
    persistence_2_day_adjustment: int = Form(10),
    persistence_4_day_adjustment: int = Form(20),
    velocity_window_hours: int = Form(6),
    velocity_baseline_days: int = Form(7),
    velocity_multiplier: int = Form(5),
    velocity_min_count: int = Form(3),
    velocity_adjustment: int = Form(10),
    host_alert_window_hours: int = Form(24),
    host_alert_count_threshold: int = Form(10),
    host_alert_adjustment: int = Form(10),
    failure_adjustment: int = Form(20),
    success_adjustment: int = Form(-20),
):
    save_config(
        {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "mailbox_address": mailbox_address,
            "mail_folder": mail_folder,
            "teams_webhook_url": teams_webhook_url,
            "teams_dry_run": teams_dry_run,
            "escalation_cooldown_hours": escalation_cooldown_hours,
            "eset_sender_filter": eset_sender_filter,
            "eset_subject_filter": eset_subject_filter,
            "auth_mode": "delegated",
            "repeat_threshold": 3,
            "repeat_window_hours": 24,
            "escalation_cooldown_hours": 24,
            "lookback_days": 60,
            "start_date": "",
            "poll_interval_seconds": 60,
            "taxonomy_scores": taxonomy_scores.strip() or DEFAULT_TAXONOMY_SCORES,
            "use_taxonomy_weighting": use_taxonomy_weighting,
            "unknown_base_score": unknown_base_score,
            "scoring_preset": scoring_preset,
            "severity_critical_threshold": severity_critical_threshold,
            "severity_high_threshold": severity_high_threshold,
            "severity_medium_threshold": severity_medium_threshold,
            "repeated_same_host_window_hours": repeated_same_host_window_hours,
            "repeated_same_host_1_adjustment": repeated_same_host_1_adjustment,
            "repeated_same_host_2_adjustment": repeated_same_host_2_adjustment,
            "repeated_same_host_3_adjustment": repeated_same_host_3_adjustment,
            "campaign_endpoint_window_hours": campaign_endpoint_window_hours,
            "campaign_endpoint_2_adjustment": campaign_endpoint_2_adjustment,
            "campaign_endpoint_3_adjustment": campaign_endpoint_3_adjustment,
            "campaign_endpoint_5_adjustment": campaign_endpoint_5_adjustment,
            "persistence_2_day_adjustment": persistence_2_day_adjustment,
            "persistence_4_day_adjustment": persistence_4_day_adjustment,
            "velocity_window_hours": velocity_window_hours,
            "velocity_baseline_days": velocity_baseline_days,
            "velocity_multiplier": velocity_multiplier,
            "velocity_min_count": velocity_min_count,
            "velocity_adjustment": velocity_adjustment,
            "host_alert_window_hours": host_alert_window_hours,
            "host_alert_count_threshold": host_alert_count_threshold,
            "host_alert_adjustment": host_alert_adjustment,
            "failure_adjustment": failure_adjustment,
            "success_adjustment": success_adjustment,
        }
    )
    rescored = backfill_severity(force=True)
    return RedirectResponse(f"/settings?saved=1&rescored={rescored}", status_code=303)


@router.post("/disconnect")
def disconnect_settings():
    for key in (
        "tenant_id",
        "client_id",
        "client_secret",
        "mailbox_address",
        "mail_folder",
        "oauth_account",
        "oauth_token_cache",
        "oauth_flow",
    ):
        delete_setting(key)
    save_config({"auth_mode": "app"})
    return RedirectResponse("/settings?disconnected=1", status_code=303)


@router.post("/quick")
def save_quick_settings(
    tenant_id: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    mailbox_address: str = Form(""),
    mail_folder: str = Form(""),
    auth_mode: str = Form("delegated"),
    eset_sender_filter: str = Form(""),
    eset_subject_filter: str = Form("ESET"),
    lookback_days: int = Form(60),
    teams_dry_run: bool = Form(False),
):
    save_config(locals())
    return RedirectResponse("/dashboard?saved=1", status_code=303)


@router.post("/mailbox")
def save_mailbox_login(
    tenant_id: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    mailbox_address: str = Form(""),
    mail_folder: str = Form(""),
):
    payload = {
        "mailbox_address": mailbox_address,
        "mail_folder": mail_folder,
        "auth_mode": "delegated",
        "teams_dry_run": True,
        "lookback_days": 60,
        "poll_interval_seconds": 60,
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if client_id:
        payload["client_id"] = client_id
    if client_secret:
        payload["client_secret"] = client_secret
    save_config(payload)
    if get_config().oauth_account:
        try:
            result_summary = run_scan()
            return RedirectResponse(
                f"/dashboard?saved=1&scanned={result_summary.get('processed', 0)}",
                status_code=303,
            )
        except Exception:
            return RedirectResponse("/dashboard?saved=1&scan_failed=1", status_code=303)
    return RedirectResponse("/dashboard?saved=1", status_code=303)


@router.post("/mailbox-login")
def save_mailbox_and_login(
    tenant_id: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    mailbox_address: str = Form(""),
    mail_folder: str = Form(""),
):
    payload = {
        "mailbox_address": mailbox_address,
        "mail_folder": mail_folder,
        "auth_mode": "delegated",
        "teams_dry_run": True,
        "lookback_days": 60,
        "poll_interval_seconds": 60,
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if client_id:
        payload["client_id"] = client_id
    if client_secret:
        payload["client_secret"] = client_secret
    save_config(payload)
    return RedirectResponse("/auth/login", status_code=303)
