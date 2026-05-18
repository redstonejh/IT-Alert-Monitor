import json
import logging
from urllib.parse import quote

import msal
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.graph_client import DELEGATED_SCOPES
from app.oauth import local_redirect_uri
from app.scanner import run_scan
from app.storage import delete_setting, get_config, get_setting, save_config, save_setting

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)


def _authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id or 'common'}"


def _build_app(cache: msal.SerializableTokenCache):
    config = get_config()
    if not config.client_id:
        raise ValueError("Client ID is required before Microsoft sign-in.")
    if config.client_secret:
        return msal.ConfidentialClientApplication(
            config.client_id,
            authority=_authority(config.tenant_id),
            client_credential=config.client_secret,
            token_cache=cache,
        )
    return msal.PublicClientApplication(
        config.client_id,
        authority=_authority(config.tenant_id),
        token_cache=cache,
    )


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    serialized = get_setting("oauth_token_cache")
    if serialized:
        cache.deserialize(serialized)
    return cache


@router.get("/login")
def login(request: Request):
    try:
        cache = _load_cache()
        app = _build_app(cache)
        redirect_uri = local_redirect_uri(request)
        flow = app.initiate_auth_code_flow(
            scopes=DELEGATED_SCOPES,
            redirect_uri=redirect_uri,
            prompt="select_account",
        )
        save_setting("oauth_flow", json.dumps(flow), sensitive=True)
        return RedirectResponse(flow["auth_uri"], status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/dashboard?auth_error={quote(str(exc))}", status_code=303)


@router.get("/callback", name="auth_callback")
def auth_callback(request: Request):
    try:
        flow_json = get_setting("oauth_flow")
        if not flow_json:
            raise ValueError("No pending Microsoft sign-in flow was found.")
        cache = _load_cache()
        app = _build_app(cache)
        result = app.acquire_token_by_auth_code_flow(json.loads(flow_json), dict(request.query_params))
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Microsoft sign-in failed."))
        if cache.has_state_changed:
            save_setting("oauth_token_cache", cache.serialize(), sensitive=True)
        claims = result.get("id_token_claims", {})
        account = claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""
        save_config({"auth_mode": "delegated", "oauth_account": account, "teams_dry_run": True})
        delete_setting("oauth_flow")
        try:
            result_summary = run_scan()
            return RedirectResponse(
                f"/dashboard?signed_in=1&scanned={result_summary.get('processed', 0)}",
                status_code=303,
            )
        except Exception:
            logger.exception("Automatic mailbox scan after sign-in failed")
            return RedirectResponse("/dashboard?signed_in=1&scan_failed=1", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/dashboard?auth_error={quote(str(exc))}", status_code=303)


@router.post("/logout")
def logout():
    delete_setting("oauth_token_cache")
    delete_setting("oauth_flow")
    save_config({"auth_mode": "app", "oauth_account": ""})
    return RedirectResponse("/dashboard?signed_out=1", status_code=303)
