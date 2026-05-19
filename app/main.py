import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_app_settings
from app.database import init_db
from app.storage import get_config
from app.logger import setup_logging
from app.routes import actions, alerts, api, auth, dashboard, settings
from app.routes import acronis, acronis_settings
from app.scanner import DEFAULT_POLL_INTERVAL_SECONDS, backfill_severity, run_scan

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


def create_app() -> FastAPI:
    setup_logging()
    init_db()
    app = FastAPI(title="ESET Outlook Alert Parser")
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(dashboard.router)
    app.include_router(settings.router)
    app.include_router(api.router)
    app.include_router(auth.router)
    app.include_router(alerts.router)
    app.include_router(actions.router)
    app.include_router(acronis.router)
    app.include_router(acronis_settings.router)

    @app.on_event("startup")
    async def start_polling() -> None:
        await asyncio.to_thread(backfill_severity, True)
        interval = get_config().poll_interval_seconds or DEFAULT_POLL_INTERVAL_SECONDS
        if interval > 0:
            asyncio.create_task(_poll_forever(interval))

    @app.exception_handler(Exception)
    async def handle_exception(request: Request, exc: Exception) -> HTMLResponse:
        logger.exception("Unhandled request error")
        return templates.TemplateResponse(
            "base.html",
            {"request": request, "error": str(exc), "content_template": None},
            status_code=500,
        )

    return app


async def _poll_forever(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(run_scan)
        except Exception:
            logger.exception("Scheduled scan failed")


app = create_app()
