# Infrastructure (Bicep)

`main.bicep` creates one resource group, `rg-<environment>`, and one module per service. Every service has key-based auth disabled; the app and the person running `azd` reach data through Entra ID roles.

| Module | Resource | SKU |
| --- | --- | --- |
| `identity.bicep` | User-assigned managed identity for the app | |
| `monitoring.bicep` | Log Analytics + Application Insights | Pay as you go |
| `storage.bicep` | Storage account, `case-documents` container | Standard LRS |
| `search.bicep` | Azure AI Search | Free |
| `docintel.bicep` | Document Intelligence | F0 |
| `foundry.bicep` | Foundry resource, project, chat + embedding deployments, tracing connection | S0, Global Standard |
| `cosmos.bicep` | Cosmos DB for NoSQL: `cases`, `drafts`, `audit_events` | Free tier |
| `containerapp.bicep` | Container Apps environment, Container Registry, web app with Easy Auth | Consumption, Basic |
| `apim.bicep` | API Management AI gateway for model calls (only when `DEPLOY_APIM=true`) | Developer |
| `keyvault.bicep` | Key Vault with RBAC | Standard |
| `budget.bicep` | Monthly budget alert (only if `BUDGET_ALERT_EMAIL` is set) | |


## Provision

```bash
azd env new caa-dev
azd env set AZURE_LOCATION eastus2
azd env set BUDGET_ALERT_EMAIL you@example.com   # optional
azd env set AZURE_SEARCH_LOCATION centralus      # optional: Free Search capacity is often full in busy regions
azd provision
azd env get-values
```

## Deploy the web app with sign-in

Docker must be running, because `azd deploy` builds the image locally and pushes it to the registry.

```bash
azd deploy                      # build, push, and roll out a new revision
./scripts/entra_app.sh          # app registration, roles, and AUTH_CLIENT_ID
azd provision                   # turns on Easy Auth with that client id
azd env get-value WEB_URL
```

Until sign-in is on, every page except `/healthz` returns 401, because the app only trusts identities that Easy Auth passes in.

The app scales to zero when idle, so the first request after a quiet spell takes a few seconds while a replica starts.

## Tear down

```bash
./scripts/teardown.sh
```

## Validate locally

```bash
az bicep build --file infra/main.bicep
```

## API Management (AI gateway), for demos only

With `DEPLOY_APIM=true`, the app's direct model calls (extraction and embeddings) go through API Management instead of straight to Foundry. Policies are in `apim-policies/`:

- `openai-api.xml`: only the app's managed identity and the deployer may call (Entra token, `oid` allow list, no subscription keys). APIM then calls Foundry with its own managed identity.
- `responses-operation.xml`: a per-caller tokens-per-minute limit (`llm-token-limit`, default 20,000, so a runaway caller gets 429 before it uses the deployment's whole quota) and token counts sent to Application Insights (`llm-emit-token-metric`, namespace `caa`).

Agent calls go to the Foundry project, which calls its models itself, so they do not pass through this gateway.

Developer tier costs about $0.07 an hour and takes 30 to 45 minutes to create, so turn it on for a demo and off afterwards:

```bash
azd env set DEPLOY_APIM true && azd provision
azd env get-values > .env      # local runs now use the gateway too

./scripts/apim_off.sh          # afterwards: back to direct calls, delete and purge APIM
```

Token metrics appear in Application Insights under Metrics, custom namespace `caa`, or with `customMetrics | where name endswith "Tokens"` in Logs.

## Continuous deployment (GitHub Actions)

`.github/workflows/azure-dev.yml` runs on pushes to `main` that change app code, and on demand. It signs in with OpenID Connect (no Azure secret in GitHub), loads the environment's settings with `azd env refresh`, runs the extraction eval as a gate, and then runs `azd deploy`. It never runs `azd provision`: infrastructure changes stay a reviewed, manual step.

One-time setup:

```bash
./scripts/github_oidc.sh
```

In production, scope the GitHub identity to the resource group instead of the subscription, and give it only the data roles the eval needs.
