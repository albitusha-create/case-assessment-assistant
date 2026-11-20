#!/usr/bin/env bash
# One-time setup for the deploy workflow (.github/workflows/azure-dev.yml).
#
# `azd pipeline config` creates an Entra identity with a federated credential
# that trusts this GitHub repository (OpenID Connect, no stored secret), gives
# it Contributor on the subscription, and sets the AZURE_* repository
# variables the workflow reads. Then the identity gets the same data roles as
# the deployer, so the eval gate can read Search and call the model.
set -euo pipefail

ENV_NAME="$(azd env get-value AZURE_ENV_NAME)"

azd pipeline config --provider github --auth-type federated \
  --principal-name "caa-github-${ENV_NAME}"

# Keep the tenant and subscription ids out of public run logs: secrets are
# masked, variables are not.
for NAME in AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID; do
  if VALUE="$(gh variable get "$NAME" 2>/dev/null)"; then
    gh secret set "$NAME" --body "$VALUE"
    gh variable delete "$NAME"
  fi
done

CLIENT_ID="$(gh variable get AZURE_CLIENT_ID)"
CI_PRINCIPAL_ID="$(az ad sp show --id "$CLIENT_ID" --query id -o tsv)"
azd env set CI_PRINCIPAL_ID "$CI_PRINCIPAL_ID"

echo
echo "Granting data roles to the GitHub identity (azd provision)"
azd provision

echo
echo "Done. Run the workflow from the Actions tab, or: gh workflow run deploy"
