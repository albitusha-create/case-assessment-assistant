"""FastAPI entry point. Run with `uvicorn caa.main:create_app --factory`.

`create_app` takes the store and the case runner as arguments so tests can pass
in-memory fakes. With no arguments it uses Cosmos DB when an endpoint is set,
and builds the Azure clients the first time a case is run.
"""

from datetime import date

from azure.identity import DefaultAzureCredential
from fastapi import FastAPI

from caa import __version__
from caa.agents.pipeline import CaseRun, Services, run_case, services_from_settings
from caa.api.routes import router
from caa.api.workflow import CaseRunner
from caa.config import get_settings
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


def create_app(store: Store | None = None, runner: CaseRunner | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)
    app.state.store = store or default_store()
    app.state.runner = runner or default_runner()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe used by Container Apps."""
        return {"status": "ok", "version": __version__}

    app.include_router(router)
    return app
