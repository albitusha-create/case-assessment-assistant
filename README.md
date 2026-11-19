# Case Assessment Assistant

An Azure-native reference implementation of an AI-assisted case assessment workflow for county human services and behavioral health programs. AI extracts facts with citations, drafts assessment sections, and checks drafts against a QA checklist. Staff review, edit and approve everything. **AI never makes clinical or eligibility decisions.**

> Status: under construction. This repo uses **synthetic data only**. It contains no real people, agencies or protected health information, and it is not a compliance certification.

## The problem

Caseworkers spend hours reviewing large case files, writing assessment narratives, and responding to QA reviews that vary from reviewer to reviewer. Late assessments affect billing compliance and, more importantly, delay services.

## The workflow

1. A caseworker uploads case documents (intake notes, collateral records, prior assessments).
2. **Extraction:** structured facts are pulled out, each with a citation to its source page or section.
3. **Drafting agent:** drafts the assessment sections; every claim is cited.
4. **QA agent:** checks the draft against a criteria checklist (completeness, citation coverage, contradictions, missing required elements) and returns a gap report.
5. **Human review:** the caseworker edits and approves; the system logs who approved what.

## Design principle: deterministic rules, LLM judgment

Business rules (required sections, checklist logic, deadline calculations) are plain Python with unit tests. The agents call them as tools. The LLM handles interpretation, drafting and synthesis only.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the component diagram and request flow.

## Azure services and why

| Service | Role |
| --- | --- |
| Microsoft Foundry Agent Service | Hosts the Drafting and QA agents, tracing and evaluations |
| Azure AI Document Intelligence | Layout extraction with page numbers for citations |
| Azure AI Search | Hybrid (keyword + vector) retrieval, filtered per case |
| Azure Blob Storage | Uploaded documents |
| Azure Cosmos DB | Cases, drafts and the append-only audit log |
| Azure Container Apps | Runs the FastAPI app and UI |
| Azure API Management | AI gateway: token limits and usage metrics |
| Microsoft Entra ID, managed identity, Key Vault | Sign-in, roles, keyless service access |
| Application Insights | Telemetry and traces |

Details and tradeoffs live in the [ADRs](docs/adr/).

## Security and compliance model

See [docs/security-compliance.md](docs/security-compliance.md).

## Evaluation approach

Coming soon.

## Cost

See [docs/cost.md](docs/cost.md).

## Deploy and tear down

Coming soon. Deployment uses the Azure Developer CLI (`azd up`) and teardown uses `scripts/teardown.sh`.

## Local development

```bash
uv sync
uv run pytest
uv run uvicorn caa.main:app --reload
```

After `azd provision`, load the synthetic cases into Azure:

```bash
azd env get-values > .env              # endpoints and names only, no keys
uv run python scripts/seed_data.py     # blob, layout, chunk, embed, index
uv run pytest -m integration           # every search hit stays inside its case
uv run python -m caa.extraction case-001   # cited facts for one case
uv run python evals/extraction_recall.py   # recall against the planted facts
uv run python -m caa.agents publish         # create the Drafting agent in Foundry
uv run python -m caa.agents draft case-002  # extract, then draft with citations
```

## Production next steps

Coming soon.

## License

[MIT](LICENSE)
