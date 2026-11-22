"""FastAPI entry point. Run with `uvicorn caa.main:create_app --factory`.

`create_app` takes the store, the case runner and the section checker as arguments so tests can pass
in-memory fakes. With no arguments it uses Cosmos DB when an endpoint is set,
and builds the Azure clients the first time a case is run.
"""

import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from caa import __version__
from caa.agents.pipeline import CaseRun, Services, run_case, services_from_settings
from caa.api import assist
from caa.api.routes import html_or_json_error, router
from caa.api.workflow import CaseRunner
from caa.assist.section_check import SectionCheck, SectionChecker, check_section
from caa.config import get_settings
from caa.integrations import portal_webhook
from caa.mcp_tools.server import build_mcp_server
from caa.portal import api as portal_api
from caa.portal import pages as portal_pages
from caa.portal.form import Domain
from caa.portal.store import PortalStore
from caa.portal.webhooks import webhook_sender
from caa.retrieval.search import list_case_chunks
from caa.storage.store import CosmosStore, MemoryStore, Store
from caa.synthetic import SyntheticCase


def default_store() -> Store:
    settings = get_settings()
    if settings.azure_cosmos_endpoint:
        return CosmosStore(
            settings.azure_cosmos_endpoint, settings.azure_cosmos_database, DefaultAzureCredential()
        )
    return MemoryStore()


def lazy_services() -> Callable[[], Services]:
    """Azure clients built on first use, so the app starts without Azure."""
    built: list[Services] = []

    def get() -> Services:
        if not built:
            built.append(services_from_settings(get_settings()))
        return built[0]

    return get


def default_runner(services: Callable[[], Services]) -> CaseRunner:
    def runner(case: SyntheticCase) -> CaseRun:
        return run_case(services(), case, date.today())

    return runner


def default_checker(services: Callable[[], Services]) -> SectionChecker:
    def checker(case_id: str, domain: Domain, text: str) -> SectionCheck:
        s = services()
        chunks = list_case_chunks(s.clients.search, case_id)
        return check_section(
            s.clients.openai, s.chat_deployment, s.criteria, case_id, domain, text, chunks
        )

    return checker


def create_app(
    store: Store | None = None,
    runner: CaseRunner | None = None,
    portal: PortalStore | None = None,
    section_checker: SectionChecker | None = None,
) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.store = store or default_store()
    services = lazy_services()
    app.state.runner = runner or default_runner(services)
    app.state.section_checker = section_checker or default_checker(services)
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
    app.include_router(assist.router)
    app.include_router(portal_api.router)
    app.include_router(portal_pages.router)
    app.include_router(portal_webhook.router)
    # MCP tools at /mcp: same portal client and approval gate, for agents.
    mcp_server = build_mcp_server(app)
    mcp_app = mcp_server.streamable_http_app(stateless_http=True, json_response=True)
    app.router.routes.extend(mcp_app.routes)
    return app
