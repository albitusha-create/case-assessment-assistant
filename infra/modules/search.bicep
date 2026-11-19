// Azure AI Search, Free tier, Entra auth only (API keys disabled).
param name string
param location string
param tags object
param principals array

var indexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var serviceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0' // create and update indexes
var roleIds = [ indexDataContributor, serviceContributor ]

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: 'free' }
  properties: {
    disableLocalAuth: true
    semanticSearch: 'disabled'
  }
}

resource roles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for pair in flatten(map(principals, p => map(roleIds, r => { principal: p, role: r }))): {
  scope: search
  name: guid(search.id, pair.principal.id, pair.role)
  properties: {
    principalId: pair.principal.id
    principalType: pair.principal.type
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', pair.role)
  }
}]

output endpoint string = 'https://${search.name}.search.windows.net'
