# 0001. Host the app on Azure Container Apps

- Status: accepted
- Date: 2026-11-19

## Context

The app is one FastAPI service with a server-rendered UI. It needs Entra sign-in, managed identity, a path to scale, and near-zero cost when nobody is using it, because this is a reference build that is idle most of the time.

## Decision

Run the container on Azure Container Apps (consumption plan), with minimum replicas set to 0 by default and 1 during demos. Use built-in authentication (Easy Auth) for Entra sign-in.

## Alternatives considered

- **App Service (Linux, B1).** Simplest PaaS for web apps and a fine choice for customers standardized on it. Rejected here because it bills every hour whether used or not, and it does not scale to zero.
- **AKS.** The right answer when a customer already runs Kubernetes or needs node-level control, service mesh, or many services. Rejected for one service: cluster and node costs, upgrades, ingress and more YAML to own.

## Consequences

- Idle cost is close to zero inside the monthly free grant.
- Revisions with traffic splitting give safe rollouts without extra tooling.
- A cold start of a few seconds after scale to zero; set minimum replicas to 1 for demos.
- The same image runs on AKS later, so this does not close that door.
