# Security and compliance model

This repository uses synthetic data only. This document describes how the design would map to controls in a real deployment. It is not legal advice or a compliance certification.

## Identity and access

- People sign in with Microsoft Entra ID. Two app roles: `Caseworker` (upload, generate, edit) and `Supervisor` (approve, view audit log).
- Services use one user-assigned managed identity with least-privilege data-plane roles. Key-based auth is disabled on every service that supports it. See [ADR 0005](adr/0005-identity-managed-identity-app-roles.md).
- Retrieval is always scoped to one case. See [ADR 0003](adr/0003-retrieval-single-index-case-filter.md).

## Networking

The reference build uses public endpoints protected by Entra auth. A production deployment would add:

- A Container Apps environment in a virtual network.
- Private endpoints for Storage, AI Search (Basic or above), Cosmos DB, Foundry, Document Intelligence and Key Vault, with public network access disabled.
- API Management in internal mode.

## Mapping to HIPAA and 42 CFR Part 2 style controls

| Control area | Real deployment requirement | How this design addresses it |
| --- | --- | --- |
| Access control (HIPAA 164.312(a)) | Unique user IDs, least privilege | Entra ID, app roles, case-scoped retrieval, managed identities |
| Audit controls (164.312(b)) | Record who accessed and changed what | Append-only audit events, App Insights traces, Azure activity logs |
| Integrity (164.312(c)) | Protect records from improper change | AI draft and human edits stored separately; approval is an explicit signed-in action |
| Transmission security (164.312(e)) | Encrypt in transit | TLS everywhere; private endpoints in production |
| Minimum necessary | Use only the data needed | Per-case retrieval filter; agents see only one case's chunks |
| Part 2 consent and redisclosure | Substance use disorder records need consent and redisclosure notices | Production: consent flag per document, excluded from retrieval without recorded consent; redisclosure notice on exports |
| Business associate agreement, residency | BAA with the cloud provider, in-region processing | Production: sign the BAA, pin one region, prefer regional model deployments |
| Prompt and trace retention | Prompts can contain PHI | Production: PHI-appropriate retention and access on the log workspace; disable content capture in tracing |

## Responsible AI

- Human in the loop by design: nothing is final until a person approves it.
- The AI never makes clinical, eligibility, risk level or level of care decisions. A deterministic rule flags such wording.
- Model deployments use Foundry content filters and prompt shields.
- Groundedness and citation coverage evaluations run in CI as a quality gate.
