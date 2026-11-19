// Document Intelligence (F0, 500 free pages a month). A custom subdomain is
// required for Entra auth; local (key) auth is disabled.
param name string
param location string
param tags object
param principals array

var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource docintel 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: { name: 'F0' }
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource roles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in principals: {
  scope: docintel
  name: guid(docintel.id, p.id, cognitiveServicesUser)
  properties: {
    principalId: p.id
    principalType: p.type
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
  }
}]

output endpoint string = docintel.properties.endpoint
