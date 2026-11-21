"""FastAPI entry point. Run with `uvicorn caa.main:create_app --factory`.

`create_app` takes the store and the case runner as arguments so tests can pass
in-memory fakes. With no arguments it uses Cosmos DB when an endpoint is set,
and builds the Azure clients the first time a case is run.
"""

import secrets
from datetime import date
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from caa import __version__
from caa.agents.pipeline import CaseRun, Services, run_case, services_from_settings
from caa.api.routes import html_or_json_error, router
from caa.api.workflow import CaseRunner
from caa.config import get_settings
from caa.integrations import portal_webhook
from caa.portal import api as portal_api
from caa.portal import pages as portal_pages
from caa.portal.store import PortalStore
from caa.portal.webhooks import webhook_sender
from caa.storage.store import CosmosStore, MemoryStore, Store
from caa.synthetic import SyntheticCase


def default_store() -> Store:
    settings = get_settings()
    if settings.azure_cosmos_endpoint:
        return CosmosStore(
            settings.azure_cosmos_endpoint, settings.azure_cosmos_database, DefaultAzureCredential()
        )
    return MemoryStore()


def default_runner() -> CaseRunner:
    services: list[Services] = []  # built on first use, so the app starts without Azure

    def runner(case: SyntheticCase) -> CaseRun:
        if not services:
            services.append(services_from_settings(get_settings()))
        return run_case(services[0], case, date.today())

    return runner


def create_app(
    store: Store | None = None,
    runner: CaseRunner | None = None,
    portal: PortalStore | None = None,
) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)
    app.state.store = store or default_store()
    app.state.runner = runner or default_runner()
    # The mock agency portal runs in the same container but keeps its own state.
    # Our app reaches it only over HTTP, through `portal_http`, like any vendor API.
    app.state.portal = portal or PortalStore.seeded()
    app.state.portal_api_key = settings.portal_api_key or (
        "" if settings.environment == "local" else secrets.token_urlsafe(32)
    )
    app.state.portal_http = httpx.Client(base_url=settings.portal_base_url, timeout=10)
    app.state.portal.listeners.append(
        webhook_sender(lambda: app.state.portal_http, app.state.portal_api_key)
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe used by Container Apps."""
        return {"status": "ok", "version": __version__}

    app.add_exception_handler(StarletteHTTPException, html_or_json_error)
    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(router)
    app.include_router(portal_api.router)
    app.include_router(portal_pages.router)
    app.include_router(portal_webhook.router)
    return app
