#!/usr/bin/env bash
# Turn the API Management gateway off after a demo: point the app back at
# Foundry, then delete APIM and purge it (APIM is soft-deleted for 48 hours,
# which would block re-creating it under the same name).
set -euo pipefail

RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
LOCATION="$(azd env get-value AZURE_LOCATION)"

azd env set DEPLOY_APIM false
azd provision
azd env get-values > .env

for APIM in $(az apim list -g "$RG" --query "[].name" -o tsv); do
  echo "Deleting ${APIM} (this can take a few minutes)"
  az apim delete -n "$APIM" -g "$RG" --yes
  az apim deletedservice purge --service-name "$APIM" --location "$LOCATION"
done
echo "APIM is off. Model calls go straight to Foundry again."
