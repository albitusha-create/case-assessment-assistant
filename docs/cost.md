# Cost

Estimates in USD per month if left running all month, November 2026 list prices. Several official pricing pages did not render prices when checked; figures marked approximate come from third-party price trackers. Confirm in the [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/).

| Service | SKU | Est. USD / month | Notes |
| --- | --- | --- | --- |
| API Management | Developer | ~48 (approximate) | Billed hourly (~$0.07); deploy only for demo hours |
| Container Registry | Basic | ~5 (approximate) | |
| Foundry models | Mini chat model, `text-embedding-3-small` | 2 to 10 | Pay per token |
| Log Analytics, App Insights | Pay as you go | 0 to 3 | Low ingestion |
| Storage, Key Vault | Standard | under 1 | |
| Container Apps | Consumption | 0 | Free grant: 180,000 vCPU-seconds, 360,000 GiB-seconds, 2M requests |
| AI Search | Free | 0 | Basic is ~74 (approximate) if needed |
| Document Intelligence | F0 | 0 | 500 pages free per month |
| Cosmos DB | Free tier | 0 | 1,000 RU/s and 25 GB; one per subscription; choose at creation |

Without APIM: about $10 to $15. With APIM Developer on all month: about $60 to $65. Deploying APIM only for the hours it is needed keeps the total close to the lower figure.

## Keeping cost down

- `azd down --force --purge` (via `scripts/teardown.sh`) between sessions.
- Container Apps minimum replicas 0 when idle.
- A $20 monthly budget alert is created by the Bicep template.
