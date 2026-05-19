from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.acronis_scanner import run_acronis_scan
from app.routes.acronis import _format_datetime
from app.security import mask_secret
from app.storage import (
    delete_setting,
    get_acronis_config,
    get_config,
    get_setting,
    get_state,
    save_acronis_config,
    save_config,
)

router = APIRouter(prefix="/acronis/settings")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def acronis_settings_page(request: Request):
    acronis = get_acronis_config()
    shared = get_config()
    last_scan_display = _format_datetime(get_state("acronis_last_scan_time"))
    display = {
        "acronis_tenant_id": acronis.tenant_id,
        "acronis_client_id": acronis.client_id,
        "acronis_client_secret_masked": mask_secret(acronis.client_secret),
        "acronis_mailbox_address": acronis.mailbox_address,
        "acronis_mail_folder": acronis.mail_folder,
        "acronis_sender_filter": acronis.sender_filter,
        "acronis_subject_filter": acronis.subject_filter,
        "acronis_taxonomy_scores": get_setting("acronis_taxonomy_scores"),
        "teams_webhook_url_masked": mask_secret(shared.teams_webhook_url),
        "teams_dry_run": shared.teams_dry_run,
        "escalation_cooldown_hours": shared.escalation_cooldown_hours,
        "last_scan_display": last_scan_display,
    }
    return templates.TemplateResponse(
        "acronis_settings.html", {"request": request, "config": display}
    )


@router.post("")
def save_acronis_settings(
    acronis_tenant_id: str = Form(""),
    acronis_client_id: str = Form(""),
    acronis_client_secret: str = Form(""),
    acronis_mailbox_address: str = Form(""),
    acronis_mail_folder: str = Form(""),
    teams_webhook_url: str = Form(""),
    teams_dry_run: bool = Form(False),
    escalation_cooldown_hours: int = Form(24),
    acronis_sender_filter: str = Form(""),
    acronis_subject_filter: str = Form(""),
    acronis_taxonomy_scores: str = Form(""),
):
    save_acronis_config(
        {
            "acronis_tenant_id": acronis_tenant_id,
            "acronis_client_id": acronis_client_id,
            "acronis_client_secret": acronis_client_secret,
            "acronis_mailbox_address": acronis_mailbox_address,
            "acronis_mail_folder": acronis_mail_folder,
            "acronis_auth_mode": "delegated",
            "acronis_lookback_days": 60,
            "acronis_start_date": "",
            "acronis_sender_filter": acronis_sender_filter,
            "acronis_subject_filter": acronis_subject_filter,
            "acronis_taxonomy_scores": acronis_taxonomy_scores.strip(),
        }
    )
    save_config(
        {
            "teams_webhook_url": teams_webhook_url,
            "teams_dry_run": teams_dry_run,
            "escalation_cooldown_hours": escalation_cooldown_hours,
        }
    )
    scanned = 0
    if acronis_client_id and acronis_mailbox_address:
        try:
            result = run_acronis_scan()
            scanned = result.get("processed", 0)
        except Exception:
            return RedirectResponse("/acronis/settings?saved=1&scan_failed=1", status_code=303)
    return RedirectResponse(f"/acronis/settings?saved=1&scanned={scanned}", status_code=303)


@router.post("/disconnect")
def disconnect_acronis_settings():
    for key in (
        "acronis_tenant_id",
        "acronis_client_id",
        "acronis_client_secret",
        "acronis_mailbox_address",
        "acronis_mail_folder",
        "acronis_sender_filter",
        "acronis_subject_filter",
    ):
        delete_setting(key)
    from app.storage import update_state

    update_state("acronis_scan_coverage_start", "")
    update_state("acronis_scan_coverage_end", "")
    update_state("acronis_last_scan_time", "")
    return RedirectResponse("/acronis/settings?disconnected=1", status_code=303)
