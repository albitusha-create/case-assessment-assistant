"""FastAPI entry point. Routes are added feature by feature."""

from fastapi import FastAPI

from caa import __version__
from caa.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe used by Container Apps."""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
