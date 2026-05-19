from dataclasses import asdict

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.security import mask_secret
from app.storage import get_config, get_setting, save_config, save_setting

router = APIRouter(prefix="/acronis/settings")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def acronis_settings_page(request: Request):
    config = get_config()
    display = asdict(config)
    display["client_secret_masked"] = mask_secret(config.client_secret)
    display["teams_webhook_url_masked"] = mask_secret(config.teams_webhook_url)
    display["client_secret"] = ""
    display["teams_webhook_url"] = ""
    display["acronis_sender_filter"] = get_setting("acronis_sender_filter")
    display["acronis_subject_filter"] = get_setting("acronis_subject_filter")
    display["acronis_taxonomy_scores"] = get_setting("acronis_taxonomy_scores")
    return templates.TemplateResponse(
        "acronis_settings.html", {"request": request, "config": display}
    )


@router.post("")
def save_acronis_settings(
    tenant_id: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    mailbox_address: str = Form(""),
    mail_folder: str = Form(""),
    teams_webhook_url: str = Form(""),
    teams_dry_run: bool = Form(False),
    escalation_cooldown_hours: int = Form(24),
    acronis_sender_filter: str = Form(""),
    acronis_subject_filter: str = Form(""),
    acronis_taxonomy_scores: str = Form(""),
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
        }
    )
    save_setting("acronis_sender_filter", acronis_sender_filter)
    save_setting("acronis_subject_filter", acronis_subject_filter)
    save_setting("acronis_taxonomy_scores", acronis_taxonomy_scores.strip())
    return RedirectResponse("/acronis/settings?saved=1", status_code=303)
