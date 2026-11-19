#!/usr/bin/env bash
# Delete everything this azd environment created, and purge soft-deleted
# Key Vault and Foundry resources so the same names can be reused.
set -euo pipefail

ENV_NAME="$(azd env get-value AZURE_ENV_NAME 2>/dev/null || true)"
echo "Tearing down azd environment: ${ENV_NAME:-unknown}"

azd down --force --purge

echo
echo "Resource groups still tagged for this project (should be empty):"
az group list --tag project=case-assessment-assistant --query "[].name" -o tsv

echo
echo "Done. The Entra app registration (if created) is not deleted; remove it"
echo "in Entra ID > App registrations when you are finished with the project."
