// Cosmos DB for NoSQL on the free tier (1,000 RU/s and 25 GB free; one per
// subscription; must be chosen at creation). Keys disabled; data-plane RBAC.
param name string
param location string
param tags object
param principals array

var databaseName = 'caa'
var containers = [ 'cases', 'drafts', 'audit_events' ]
// Built-in "Cosmos DB Built-in Data Contributor" (data plane, not Azure RBAC).
var dataContributor = '00000000-0000-0000-0000-000000000002'

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    disableLocalAuth: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [ { locationName: location, failoverPriority: 0, isZoneRedundant: false } ]
  }
}

// Shared database throughput stays inside the free 1,000 RU/s.
resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: account
  name: databaseName
  properties: {
    resource: { id: databaseName }
    options: { throughput: 1000 }
  }
}

resource sqlContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = [for c in containers: {
  parent: database
  name: c
  properties: {
    resource: {
      id: c
      partitionKey: { paths: [ '/case_id' ], kind: 'Hash' }
    }
  }
}]

resource roles 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = [for p in principals: {
  parent: account
  name: guid(account.id, p.id, dataContributor)
  properties: {
    principalId: p.id
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributor}'
    scope: account.id
  }
}]

output endpoint string = account.properties.documentEndpoint
output databaseName string = databaseName
