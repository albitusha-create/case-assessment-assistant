# Small, non-root image for Azure Container Apps.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY criteria ./criteria
COPY data/synthetic/source ./data/synthetic/source
# The mock agency portal serves these synthetic PDFs as case attachments.
COPY data/synthetic/cases ./data/synthetic/cases
RUN uv sync --frozen --no-dev

RUN useradd --uid 10001 --no-create-home appuser
USER appuser
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "caa.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
