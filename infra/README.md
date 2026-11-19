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
| `keyvault.bicep` | Key Vault with RBAC | Standard |
| `budget.bicep` | Monthly budget alert (only if `BUDGET_ALERT_EMAIL` is set) | |

Container Apps and API Management are added in later steps.

## Provision

```bash
azd env new caa-dev
azd env set AZURE_LOCATION eastus2
azd env set BUDGET_ALERT_EMAIL you@example.com   # optional
azd provision
azd env get-values
```

## Tear down

```bash
./scripts/teardown.sh
```

## Validate locally

```bash
az bicep build --file infra/main.bicep
```
