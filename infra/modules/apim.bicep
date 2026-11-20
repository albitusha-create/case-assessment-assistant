// API Management (Developer tier) as an AI gateway in front of the Foundry
// model endpoint. The app keeps using the OpenAI v1 client; only the base URL
// changes. Policies live in infra/apim-policies.
//
// Developer tier: no SLA, about $0.07 an hour, and 30 to 45 minutes to create.
// It is deployed only when DEPLOY_APIM is true; see infra/README.md.
param name string
param location string
param tags object
param foundryAccountName string
param foundryOpenAiEndpoint string
param appInsightsName string

@description('Object ids allowed to call the gateway: the app identity and, optionally, the deployer.')
param allowedCallers array

@description('Per-caller limit for model calls.')
param tokensPerMinute int

param publisherEmail string = 'apim-admin@example.com'

var openAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var callersXml = join(map(allowedCallers, id => '<value>${id}</value>'), '')

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'Developer', capacity: 1 }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    publisherName: 'Case Assessment Assistant'
  }
}

// APIM calls the models as itself, so it needs the same inference role the app has.
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource modelRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, apim.id, openAiUser)
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUser)
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource logger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsights.id
    credentials: { instrumentationKey: appInsights.properties.InstrumentationKey }
  }
}

// Client calls <gateway>/openai/v1/responses; APIM forwards to
// <foundry>/openai/v1/responses.
resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'openai'
  properties: {
    displayName: 'Foundry models (OpenAI v1)'
    path: 'openai'
    protocols: [ 'https' ]
    serviceUrl: '${foundryOpenAiEndpoint}openai'
    subscriptionRequired: false // callers prove who they are with an Entra token instead
  }
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: replace(replace(loadTextContent('../apim-policies/openai-api.xml'),
      '__TENANT_ID__', tenant().tenantId),
      '__ALLOWED_CALLERS__', callersXml)
  }
}

resource responses 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'responses'
  properties: { displayName: 'Create response', method: 'POST', urlTemplate: '/v1/responses' }
}

resource responsesPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2024-05-01' = {
  parent: responses
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: replace(loadTextContent('../apim-policies/responses-operation.xml'),
      '__TOKENS_PER_MINUTE__', string(tokensPerMinute))
  }
}

// Embeddings pass through without a token limit: llm-token-limit covers chat
// and Responses calls, and embedding calls here are small and batched.
resource embeddings 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'embeddings'
  properties: { displayName: 'Create embeddings', method: 'POST', urlTemplate: '/v1/embeddings' }
}

// Sends request logs and the custom token metrics to Application Insights.
resource diagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = {
  parent: api
  name: 'applicationinsights'
  properties: {
    loggerId: logger.id
    metrics: true
    alwaysLog: 'allErrors'
    sampling: { samplingType: 'fixed', percentage: 100 }
  }
}

output gatewayUrl string = apim.properties.gatewayUrl
