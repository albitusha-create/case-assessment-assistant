#!/usr/bin/env bash
# Create (or update) the Entra app registration that Container Apps uses to
# sign people in, with the Caseworker and Supervisor app roles, and give you
# both roles. Safe to run more than once.
#
# Order: `azd provision` and `azd deploy` first (this script needs the app's
# URL), then this script, then `azd provision` again so the template turns
# sign-in on with the client id this script saves.
set -euo pipefail

ENV_NAME="$(azd env get-value AZURE_ENV_NAME)"
WEB_URL="$(azd env get-value WEB_URL)"
DISPLAY_NAME="caa-${ENV_NAME}"
REDIRECT_URI="${WEB_URL}/.auth/login/aad/callback"

# Fixed role ids, so re-running the script updates the roles instead of
# replacing them (which would drop existing assignments).
CASEWORKER_ROLE_ID="2bd9fef4-aeaf-4a36-bc54-f237b73b9068"
SUPERVISOR_ROLE_ID="7360d1e8-a6a4-4fe3-aba1-55f234c126af"

ROLES_FILE="$(mktemp)"
trap 'rm -f "$ROLES_FILE"' EXIT
cat > "$ROLES_FILE" <<JSON
[
  {
    "id": "${CASEWORKER_ROLE_ID}",
    "value": "Caseworker",
    "displayName": "Caseworker",
    "description": "Runs drafting and QA on a case.",
    "allowedMemberTypes": ["User"],
    "isEnabled": true
  },
  {
    "id": "${SUPERVISOR_ROLE_ID}",
    "value": "Supervisor",
    "displayName": "Supervisor",
    "description": "Approves or returns drafts and may dismiss AI-judged QA findings.",
    "allowedMemberTypes": ["User"],
    "isEnabled": true
  }
]
JSON

echo "App registration: ${DISPLAY_NAME}"
APP_ID="$(az ad app list --display-name "$DISPLAY_NAME" --query "[0].appId" -o tsv)"
if [ -z "$APP_ID" ]; then
  APP_ID="$(az ad app create --display-name "$DISPLAY_NAME" \
    --sign-in-audience AzureADMyOrg --query appId -o tsv)"
  echo "  created ${APP_ID}"
fi

# ID token issuance is on because sign-in uses the ID token only (no client
# secret to store or rotate).
az ad app update --id "$APP_ID" \
  --web-redirect-uris "$REDIRECT_URI" \
  --enable-id-token-issuance true \
  --app-roles @"$ROLES_FILE"

SP_ID="$(az ad sp list --filter "appId eq '${APP_ID}'" --query "[0].id" -o tsv)"
if [ -z "$SP_ID" ]; then
  SP_ID="$(az ad sp create --id "$APP_ID" --query id -o tsv)"
fi

# Only people with an assigned role can sign in at all.
az ad sp update --id "$SP_ID" --set appRoleAssignmentRequired=true

USER_ID="$(az ad signed-in-user show --query id -o tsv)"
ASSIGNED="$(az rest --method GET \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}/appRoleAssignedTo" \
  --query "value[?principalId=='${USER_ID}'].appRoleId" -o tsv)"

for ROLE_ID in "$CASEWORKER_ROLE_ID" "$SUPERVISOR_ROLE_ID"; do
  if ! grep -q "$ROLE_ID" <<< "$ASSIGNED"; then
    az rest --method POST \
      --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}/appRoleAssignedTo" \
      --headers "Content-Type=application/json" \
      --body "{\"principalId\": \"${USER_ID}\", \"resourceId\": \"${SP_ID}\", \"appRoleId\": \"${ROLE_ID}\"}" \
      > /dev/null
  fi
done
echo "  you hold Caseworker and Supervisor"

azd env set AUTH_CLIENT_ID "$APP_ID"
echo
echo "Saved AUTH_CLIENT_ID. Run \`azd provision\` to turn sign-in on, then open ${WEB_URL}"
