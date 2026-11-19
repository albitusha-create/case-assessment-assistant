# 0005. Managed identity for services, Entra app roles for people

- Status: accepted
- Date: 2026-11-19

## Context

The workload handles (synthetic) sensitive case records. No keys or connection strings may live in code, config or CI. Caseworkers and supervisors need different permissions.

## Decision

- Disable local (key) authentication on every service that supports it.
- Give the Container App one user-assigned managed identity with least-privilege data-plane roles (Storage Blob Data Contributor, Search Index Data Contributor, Azure AI User, Cognitive Services User, Cosmos DB Built-in Data Contributor, Key Vault Secrets User, AcrPull).
- Use one Entra app registration with two app roles, `Caseworker` and `Supervisor`, enforced in FastAPI from the roles claim that Easy Auth passes through.
- GitHub Actions signs in with an OIDC federated credential; no deploy secret is stored.

## Alternatives considered

- **API keys in Key Vault.** Better than keys in code, but still a secret to rotate and leak. Kept only for values that cannot be an identity.
- **System-assigned identity.** Simpler, but its lifecycle is tied to the app, which makes role assignments awkward when the app is recreated.
- **On-behalf-of (OBO) for downstream calls.** Lets search and storage enforce the user's own permissions. The production next step.

## Consequences

- Nothing to rotate; access is reviewable in Azure role assignments.
- Local development uses `az login` through `DefaultAzureCredential`, so the same code runs locally and in Azure.
