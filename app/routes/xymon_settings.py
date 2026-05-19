from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.routes.xymon import _format_datetime
from app.security import mask_secret
from app.storage import delete_setting, get_state, get_xymon_config, save_xymon_config, update_state
from app.xymon_scanner import run_xymon_scan

router = APIRouter(prefix="/xymon/settings")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
@router.get("/")
def xymon_settings_page(request: Request):
    xymon = get_xymon_config()
    last_scan_display = _format_datetime(get_state("xymon_last_scan_time"))
    display = {
        "xymon_tenant_id": xymon.tenant_id,
        "xymon_client_id": xymon.client_id,
        "xymon_client_secret_masked": mask_secret(xymon.client_secret),
        "xymon_mailbox_address": xymon.mailbox_address,
        "xymon_mail_folder": xymon.mail_folder,
        "xymon_sender_filter": xymon.sender_filter,
        "xymon_subject_filter": xymon.subject_filter,
        "xymon_host_filter": xymon.host_filter,
        "xymon_test_filter": xymon.test_filter,
        "xymon_status_filter": xymon.status_filter,
        "xymon_poll_interval_seconds": xymon.poll_interval_seconds,
        "last_scan_display": last_scan_display,
    }
    return templates.TemplateResponse(
        "xymon_settings.html", {"request": request, "config": display}
    )


@router.post("")
@router.post("/")
def save_xymon_settings(
    xymon_tenant_id: str = Form(""),
    xymon_client_id: str = Form(""),
    xymon_client_secret: str = Form(""),
    xymon_mailbox_address: str = Form(""),
    xymon_mail_folder: str = Form(""),
    xymon_sender_filter: str = Form(""),
    xymon_subject_filter: str = Form(""),
    xymon_host_filter: str = Form(""),
    xymon_test_filter: str = Form(""),
    xymon_status_filter: str = Form(""),
    xymon_poll_interval_seconds: int = Form(60),
):
    save_xymon_config(
        {
            "xymon_tenant_id": xymon_tenant_id,
            "xymon_client_id": xymon_client_id,
            "xymon_client_secret": xymon_client_secret,
            "xymon_mailbox_address": xymon_mailbox_address,
            "xymon_mail_folder": xymon_mail_folder,
            "xymon_sender_filter": xymon_sender_filter,
            "xymon_subject_filter": xymon_subject_filter,
            "xymon_host_filter": xymon_host_filter,
            "xymon_test_filter": xymon_test_filter,
            "xymon_status_filter": xymon_status_filter,
            "xymon_auth_mode": "delegated",
            "xymon_lookback_days": 60,
            "xymon_start_date": "",
            "xymon_poll_interval_seconds": xymon_poll_interval_seconds,
        }
    )
    scanned = 0
    if xymon_client_id and xymon_mailbox_address:
        try:
            result = run_xymon_scan()
            scanned = result.get("processed", 0)
        except Exception:
            return RedirectResponse("/xymon/settings?saved=1&scan_failed=1", status_code=303)
    return RedirectResponse(f"/xymon/settings?saved=1&scanned={scanned}", status_code=303)


@router.post("/disconnect")
def disconnect_xymon_settings():
    for key in (
        "xymon_tenant_id",
        "xymon_client_id",
        "xymon_client_secret",
        "xymon_mailbox_address",
        "xymon_mail_folder",
        "xymon_sender_filter",
        "xymon_subject_filter",
        "xymon_host_filter",
        "xymon_test_filter",
        "xymon_status_filter",
    ):
        delete_setting(key)
    update_state("xymon_scan_coverage_start", "")
    update_state("xymon_scan_coverage_end", "")
    update_state("xymon_last_scan_time", "")
    return RedirectResponse("/xymon/settings?disconnected=1", status_code=303)
