// Microsoft Foundry resource (AIServices account with project management),
// one project, and two model deployments. Key auth is disabled.
param accountName string
param projectName string
param location string
param tags object
param principals array
param chatModelName string
param chatModelVersion string
param embeddingModelName string
param embeddingModelVersion string
param capacity int
param appInsightsId string
@secure()
param appInsightsConnectionString string

var azureAiUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'      // agents and project data plane
var openAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'       // model inference
var roleIds = [ azureAiUser, openAiUser ]

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Case Assessment Assistant'
  }
}

// Sends Foundry agent traces to the same Application Insights as the app.
resource tracing 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: appInsightsConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsightsId }
  }
}

// The account accepts one operation at a time, so deployments wait for the
// project and its connection to finish.
resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: chatModelName
  dependsOn: [ project, tracing ]
  sku: { name: 'GlobalStandard', capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: chatModelName, version: chatModelVersion }
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// Deployments on one account must be created one at a time.
resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: embeddingModelName
  dependsOn: [ chat ]
  sku: { name: 'GlobalStandard', capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: embeddingModelName, version: embeddingModelVersion }
  }
}

resource roles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for pair in flatten(map(principals, p => map(roleIds, r => { principal: p, role: r }))): {
  scope: account
  name: guid(account.id, pair.principal.id, pair.role)
  properties: {
    principalId: pair.principal.id
    principalType: pair.principal.type
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', pair.role)
  }
}]

output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${project.name}'
output openAiEndpoint string = 'https://${accountName}.openai.azure.com/'
output chatDeployment string = chat.name
output embeddingDeployment string = embedding.name
