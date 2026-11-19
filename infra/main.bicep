// Entry point for `azd provision`. Creates one resource group and wires the
// modules. Every service has key-based auth disabled; access is Entra only.
targetScope = 'subscription'

@minLength(1)
@maxLength(32)
@description('azd environment name, for example caa-dev. Used in resource names and tags.')
param environmentName string

@minLength(1)
@description('Azure region for all resources.')
param location string

@description('Object id of the person running azd, so local dev can reach data with az login.')
param principalId string = ''

@description('Region for AI Search. Free tier capacity runs out in busy regions, so it can differ from the main region; the extra latency is a few milliseconds.')
param searchLocation string = ''

@description('Email for the monthly budget alert. Leave empty to skip the budget.')
param budgetAlertEmail string = ''

@description('Monthly budget in USD for the resource group.')
param budgetAmount int = 20

@description('Chat model deployment. Must be available with Global Standard quota in the region.')
param chatModelName string = 'gpt-5.4-mini'
param chatModelVersion string = '2026-03-17'

@description('Embedding model deployment.')
param embeddingModelName string = 'text-embedding-3-small'
param embeddingModelVersion string = '1'

@description('Thousands of tokens per minute for each deployment.')
param modelCapacity int = 30

var searchRegion = empty(searchLocation) ? location : searchLocation
var tags = { 'azd-env-name': environmentName, project: 'case-assessment-assistant' }
var token = toLower(uniqueString(subscription().id, environmentName, location))

// The deployer gets the same data roles as the app, but as a User principal.
var deployer = empty(principalId) ? [] : [ { id: principalId, type: 'User' } ]

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module identity 'modules/identity.bicep' = {
  scope: rg
  name: 'identity'
  params: { name: 'id-caa-${token}', location: location, tags: tags }
}

var principals = concat([ { id: identity.outputs.principalId, type: 'ServicePrincipal' } ], deployer)

module monitoring 'modules/monitoring.bicep' = {
  scope: rg
  name: 'monitoring'
  params: { token: token, location: location, tags: tags }
}

module storage 'modules/storage.bicep' = {
  scope: rg
  name: 'storage'
  params: { name: 'stcaa${token}', location: location, tags: tags, principals: principals }
}

module search 'modules/search.bicep' = {
  scope: rg
  name: 'search'
  params: { name: 'srch-caa-${token}', location: searchRegion, tags: tags, principals: principals }
}

module docintel 'modules/docintel.bicep' = {
  scope: rg
  name: 'docintel'
  params: { name: 'di-caa-${token}', location: location, tags: tags, principals: principals }
}

module foundry 'modules/foundry.bicep' = {
  scope: rg
  name: 'foundry'
  params: {
    accountName: 'aif-caa-${token}'
    projectName: 'caa'
    location: location
    tags: tags
    principals: principals
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    capacity: modelCapacity
    appInsightsId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

module cosmos 'modules/cosmos.bicep' = {
  scope: rg
  name: 'cosmos'
  params: { name: 'cosmos-caa-${token}', location: location, tags: tags, principals: principals }
}

module keyvault 'modules/keyvault.bicep' = {
  scope: rg
  name: 'keyvault'
  params: { name: 'kv-caa-${token}', location: location, tags: tags, principals: principals }
}

module budget 'modules/budget.bicep' = if (!empty(budgetAlertEmail)) {
  scope: rg
  name: 'budget'
  params: { amount: budgetAmount, contactEmail: budgetAlertEmail }
}

// azd writes these to .azure/<env>/.env; the app reads them as settings.
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CLIENT_ID string = identity.outputs.clientId
output AZURE_FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_OPENAI_ENDPOINT string = foundry.outputs.openAiEndpoint
output CHAT_MODEL_DEPLOYMENT string = foundry.outputs.chatDeployment
output EMBEDDING_MODEL_DEPLOYMENT string = foundry.outputs.embeddingDeployment
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_DOCINTEL_ENDPOINT string = docintel.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_URL string = storage.outputs.blobEndpoint
output AZURE_STORAGE_CONTAINER string = storage.outputs.containerName
output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.endpoint
output AZURE_COSMOS_DATABASE string = cosmos.outputs.databaseName
output AZURE_KEY_VAULT_URI string = keyvault.outputs.uri
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.appInsightsConnectionString
