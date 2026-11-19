// Blob storage for uploaded case documents. Shared key access is off.
param name string
param location string
param tags object
@description('Principals that get Storage Blob Data Contributor: [{ id, type }].')
param principals array

var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'case-documents'
}

resource roles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in principals: {
  scope: account
  name: guid(account.id, p.id, blobDataContributor)
  properties: {
    principalId: p.id
    principalType: p.type
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
  }
}]

output blobEndpoint string = account.properties.primaryEndpoints.blob
output containerName string = container.name
